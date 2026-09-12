"""批量导入菜谱到隔离 Milvus Collection，支持 checkpoint 断点续跑。"""
import argparse, hashlib, json
from dataclasses import replace
from pathlib import Path
from familyos_agent.chunking import ParentChildChunker
from familyos_agent.clients.bge_m3 import BGEM3EmbeddingClient
from familyos_agent.config import load_config
from familyos_agent.domain import SourceDocument
from familyos_agent.parsing import ParserRegistry
from familyos_agent.repositories.milvus import MilvusCollectionManager

# stable_id 为相对路径生成稳定正整数。
def stable_id(value): return int(hashlib.sha256(value.encode()).hexdigest()[:15], 16)

# load_checkpoint 返回已 flush 的文档集合。
def load_checkpoint(path):
    return {json.loads(x)["source"] for x in path.read_text(encoding="utf8").splitlines() if x.strip()} if path.exists() else set()

# main 批量解析、向量化、写入，并在 flush 后追加映射和 checkpoint。
def main():
    p = argparse.ArgumentParser(); p.add_argument("--root", type=Path, required=True); p.add_argument("--config", default="config/config.yaml"); p.add_argument("--collection", default="familyos_document_chunks_eval_v1"); p.add_argument("--mapping", type=Path, default=Path("evaluation/datasets/raw/chunks.jsonl")); p.add_argument("--checkpoint", type=Path, default=Path("evaluation/datasets/raw/import.checkpoint.jsonl")); p.add_argument("--batch-documents", type=int, default=10); p.add_argument("--timeout", type=float, default=120); p.add_argument("--recreate", action="store_true"); a=p.parse_args()
    if a.collection != "familyos_document_chunks_eval_v1" or a.batch_documents <= 0: raise ValueError("只允许操作固定评估 Collection")
    cfg=load_config(a.config); mgr=MilvusCollectionManager(replace(cfg.rag.milvus, collection=a.collection, timeout=a.timeout), cfg.rag.embedding.dimensions)
    if a.recreate and mgr._client.has_collection(collection_name=a.collection): mgr._client.drop_collection(collection_name=a.collection, timeout=a.timeout); a.mapping.unlink(missing_ok=True); a.checkpoint.unlink(missing_ok=True)
    mgr.ensure_ready(); done=load_checkpoint(a.checkpoint); paths=[x for x in sorted(a.root.rglob("*.md")) if x.relative_to(a.root).as_posix() not in done]; parser=ParserRegistry(); chunker=ParentChildChunker(cfg.rag.child_size,cfg.rag.child_overlap,cfg.rag.parent_size); emb=BGEM3EmbeddingClient(cfg.rag.embedding.model_name,cfg.rag.embedding.batch_size,cfg.rag.embedding.use_fp16,cfg.rag.embedding.device); a.mapping.parent.mkdir(parents=True,exist_ok=True); a.checkpoint.parent.mkdir(parents=True,exist_ok=True)
    try:
        with a.mapping.open("a",encoding="utf8") as mf, a.checkpoint.open("a",encoding="utf8") as cf:
            for start in range(0,len(paths),a.batch_documents):
                group=paths[start:start+a.batch_documents]; parsed=[]
                for path in group:
                    rel=path.relative_to(a.root).as_posix(); src=SourceDocument(stable_id(rel),900001,900001,1,path.name,".md","text/markdown",path.read_bytes()); _,children=chunker.chunk(src,parser.resolve(".md",path.name).parse(src)); parsed.append((rel,children))
                chunks=[c for _,cs in parsed for c in cs]; vectors=emb.embed_documents([c.content for c in chunks]); rows=[]
                for c,d,s in zip(chunks,vectors.dense,vectors.sparse): rows.append({"chunk_id":c.id,"document_id":c.document_id,"knowledge_base_id":c.knowledge_base_id,"user_id":c.user_id,"index_version":c.index_version,"chunk_index":c.index,"parent_id":c.parent_id,"content_sha256":c.content_sha256,"content":c.content,"metadata":c.metadata,"active":True,"dense_vector":[float(x) for x in d],"sparse_vector":{int(k):float(v) for k,v in s.items()}})
                mgr._client.insert(collection_name=a.collection,data=rows,timeout=a.timeout); mgr._client.flush(collection_name=a.collection,timeout=a.timeout)
                for rel,cs in parsed:
                    for c in cs: mf.write(json.dumps({"source":rel,"document_id":c.document_id,"chunk_id":c.id,"parent_id":c.parent_id,"chunk_index":c.index,"content":c.content},ensure_ascii=False)+"\n")
                    cf.write(json.dumps({"source":rel,"chunks":len(cs)},ensure_ascii=False)+"\n")
                mf.flush(); cf.flush(); print(f"imported={min(start+a.batch_documents,len(paths))}/{len(paths)} chunks={len(chunks)}",flush=True)
    finally: emb.close(); mgr.close()
    print(f"completed_documents={len(done)+len(paths)}",flush=True)

if __name__ == "__main__": main()
