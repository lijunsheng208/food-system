"""通过真实 gRPC 服务验证 awaiting_input、断开和 resume 流程。"""

import argparse
import grpc

from familyos_agent.generated.agent.v1 import agent_pb2, agent_pb2_grpc


def main() -> None:
    """创建会话并执行一次断开后恢复的 ChatStream 验证。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default="127.0.0.1:50054")
    parser.add_argument("--token", required=True)
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--knowledge-base-id", type=int, required=True)
    args = parser.parse_args()
    metadata = (("x-familyos-internal-token", args.token),)
    with grpc.insecure_channel(args.target) as channel:
        client = agent_pb2_grpc.AgentChatServiceStub(channel)
        conversation = client.CreateConversation(agent_pb2.CreateConversationRequest(user_id=args.user_id, knowledge_base_id=args.knowledge_base_id), metadata=metadata)
        conversation_id = conversation.conversation_id
        first = client.ChatStream(agent_pb2.ChatStreamRequest(user_id=args.user_id, knowledge_base_id=args.knowledge_base_id, conversation_id=conversation_id, message="推荐晚餐", request_id="d3-first"), metadata=metadata)
        first_events = []
        for event in first:
            first_events.append(event.type)
            print("first", event.type, event.content)
            if event.type == "awaiting_input":
                break
        if "awaiting_input" not in first_events:
            raise RuntimeError("首次请求未进入 awaiting_input")
        answer = "4 人，无过敏原，在家做中餐"
        for attempt in range(1, 4):
            second = client.ChatStream(agent_pb2.ChatStreamRequest(user_id=args.user_id, knowledge_base_id=args.knowledge_base_id, conversation_id=conversation_id, message=answer, request_id="d3-resume-%d" % attempt), metadata=metadata)
            second_events = []
            for event in second:
                second_events.append(event.type)
                print("resume-%d" % attempt, event.type, event.content)
            if "completed" in second_events:
                return
            if "awaiting_input" not in second_events:
                raise RuntimeError("恢复请求未完成且未返回 awaiting_input")
            answer = "没有其他忌口，请直接推荐"
        raise RuntimeError("恢复请求超过最大中断次数")


if __name__ == "__main__":
    main()
