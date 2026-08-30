import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, FlatList, KeyboardAvoidingView, Platform, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { ensurePersonalKnowledgeBase } from '../services/knowledge';
import { createAgentConversation, streamAgentChat, type AgentChatEvent, type AgentChatSubscription, type AgentCitation } from '../services/agentChat';
import { colors, spacing, typography } from '../theme';

type Message = { id: string; role: 'user' | 'assistant'; content: string; citations?: AgentCitation[] };

// visibleAnswer 清理模型可能残留的内部证据编号，引用由消息底部单独展示。
function visibleAnswer(content: string): string {
  return content.replace(/\s*(?:\[C\d+\]|（?参见\s*C\d+）?)/gi, '').trim();
}

// AIScreen 提供基于个人知识库的流式 AI 对话界面。
export default function AIScreen() {
  const insets = useSafeAreaInsets();
  const [knowledgeBaseId, setKnowledgeBaseId] = useState<number | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const subscriptionRef = useRef<AgentChatSubscription | null>(null);

  useEffect(() => {
    // 对话绑定当前用户知识库，避免客户端传入未知知识库。
    void ensurePersonalKnowledgeBase().then(async (baseID) => { setKnowledgeBaseId(baseID); setConversationId(await createAgentConversation(baseID)); }).catch(() => setError('无法创建对话'));
    return () => subscriptionRef.current?.close();
  }, []);

  // sendMessage 发送问题并按 SSE 事件增量合并回答。
  const sendMessage = () => {
    const query = input.trim();
    if (!query || !knowledgeBaseId || !conversationId || loading) return;
    const assistantID = String(Date.now()) + '-assistant';
    setMessages((items) => [...items, { id: String(Date.now()) + '-user', role: 'user', content: query }, { id: assistantID, role: 'assistant', content: '' }]);
    setInput('');
    setError(null);
    setLoading(true);
    subscriptionRef.current = streamAgentChat({ knowledge_base_id: knowledgeBaseId, conversation_id: conversationId, message: query }, (event: AgentChatEvent) => {
      if (event.type === 'answer_delta') setMessages((items) => items.map((item) => item.id === assistantID ? { ...item, content: item.content + event.content } : item));
      else if (event.type === 'citation') setMessages((items) => items.map((item) => item.id === assistantID && !(item.citations || []).some((citation) => citation.document_id === event.citation.document_id) ? { ...item, citations: [...(item.citations || []), event.citation] } : item));
      else if (event.type === 'error') { setError(event.message); setLoading(false); }
      else if (event.type === 'completed') setLoading(false);
    });
  };

  // stopMessage 取消当前生成请求并恢复输入状态。
  const stopMessage = () => { subscriptionRef.current?.close(); subscriptionRef.current = null; setLoading(false); };

  return (
    <KeyboardAvoidingView style={styles.container} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}><View style={styles.brandIcon}><Ionicons name="sparkles" size={18} color={colors.textOnPrimary} /></View><View><Text style={styles.title}>助手Bot</Text><Text style={styles.subtitle}>基于你的家庭知识库</Text></View><View style={styles.online}><View style={styles.onlineDot} /><Text style={styles.onlineText}>在线</Text></View></View>
      <FlatList data={messages} keyExtractor={(item) => item.id} contentContainerStyle={[styles.list, messages.length === 0 && styles.emptyList]} keyboardShouldPersistTaps="handled" renderItem={({ item }) => (
        <View style={[styles.messageRow, item.role === 'user' && styles.userRow]}><View style={[styles.avatar, item.role === 'user' ? styles.userAvatar : styles.botAvatar]}><Ionicons name={item.role === 'user' ? 'person' : 'sparkles'} size={14} color={item.role === 'user' ? colors.primary : colors.textOnPrimary} /></View><View style={[styles.bubble, item.role === 'user' ? styles.userBubble : styles.assistantBubble]}><Text style={[styles.role, item.role === 'user' && styles.userRole]}>{item.role === 'user' ? '你' : '助手Bot'}</Text><Text style={[styles.message, item.role === 'user' && styles.userMessage]}>{item.role === 'assistant' ? visibleAnswer(item.content) || (loading ? '正在思考...' : '') : item.content}</Text>{!!item.citations?.length && <View style={styles.citationBox}><View style={styles.citationTitle}><Ionicons name="book-outline" size={13} color={colors.primary} /><Text style={styles.citationHeading}>参考来源</Text></View>{item.citations.map((citation) => <View key={citation.document_id} style={styles.sourceRow}><Ionicons name="document-text-outline" size={14} color={colors.textSecondary} /><Text style={styles.sourceName} numberOfLines={1}>{citation.document_name || `文档 #${citation.document_id}`}</Text></View>)}</View>}</View></View>
      )} ListEmptyComponent={<View style={styles.emptyState}><View style={styles.emptyIcon}><Ionicons name="chatbubble-ellipses-outline" size={28} color={colors.primary} /></View><Text style={styles.emptyTitle}>开始和助手Bot聊聊</Text><Text style={styles.empty}>可以问家庭饮食、忌口和菜谱安排</Text></View>} />
      {error && <Text style={styles.error}>{error}</Text>}
      <View style={styles.composer}><TextInput style={styles.input} value={input} onChangeText={setInput} placeholder="问问家庭饮食、菜谱或忌口..." placeholderTextColor={colors.textSecondary} multiline editable={!loading} /><TouchableOpacity style={[styles.action, loading && styles.stopAction]} onPress={loading ? stopMessage : sendMessage} accessibilityLabel={loading ? '停止生成' : '发送'}><Ionicons name={loading ? 'stop' : 'arrow-up'} size={20} color={colors.textOnPrimary} /></TouchableOpacity></View>
      {(!knowledgeBaseId || !conversationId) && <ActivityIndicator style={styles.loader} color={colors.primary} />}
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border, backgroundColor: colors.surface },
  brandIcon: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary, marginRight: spacing.sm },
  title: { fontSize: 18, fontWeight: '700', color: colors.textPrimary },
  subtitle: { fontSize: 12, color: colors.textSecondary, marginTop: 2 },
  online: { marginLeft: 'auto', flexDirection: 'row', alignItems: 'center', gap: 5 },
  onlineDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: colors.success },
  onlineText: { fontSize: 12, color: colors.success },
  list: { paddingHorizontal: spacing.md, paddingTop: spacing.lg, paddingBottom: spacing.xxxl, gap: spacing.lg, flexGrow: 1 },
  emptyList: { justifyContent: 'center' },
  messageRow: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.sm },
  userRow: { flexDirection: 'row-reverse' },
  avatar: { width: 28, height: 28, borderRadius: 14, alignItems: 'center', justifyContent: 'center', marginTop: 2 },
  botAvatar: { backgroundColor: colors.primary },
  userAvatar: { backgroundColor: colors.primaryLight },
  bubble: { maxWidth: '76%', paddingHorizontal: spacing.md, paddingVertical: 10, borderRadius: 12 },
  assistantBubble: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderBottomLeftRadius: 4 },
  role: { fontSize: 11, color: colors.textSecondary, marginBottom: 3 },
  userRole: { color: 'rgba(255,255,255,0.78)' },
  message: { color: colors.textPrimary, fontSize: 14, lineHeight: 21 },
  userMessage: { color: colors.textOnPrimary },
  userBubble: { backgroundColor: colors.primary, borderBottomRightRadius: 4 },
  citationBox: { marginTop: 10, paddingTop: 8, borderTopWidth: 1, borderTopColor: colors.border, gap: 6 },
  citationTitle: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  citationHeading: { color: colors.primary, fontSize: 12, fontWeight: '600' },
  sourceRow: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  sourceName: { flex: 1, color: colors.textSecondary, fontSize: 12 },
  emptyState: { alignItems: 'center', paddingBottom: 64 },
  emptyIcon: { width: 56, height: 56, borderRadius: 28, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primaryLight, marginBottom: spacing.md },
  emptyTitle: { fontSize: 16, fontWeight: '600', color: colors.textPrimary, marginBottom: spacing.xs },
  empty: { textAlign: 'center', color: colors.textSecondary, fontSize: 13 },
  error: { color: colors.error, paddingHorizontal: spacing.md, paddingBottom: spacing.sm },
  composer: { flexDirection: 'row', alignItems: 'flex-end', padding: spacing.md, borderTopWidth: 1, borderTopColor: colors.border, backgroundColor: colors.surface, gap: spacing.sm },
  input: { flex: 1, maxHeight: 110, minHeight: 46, borderWidth: 1, borderColor: colors.border, borderRadius: 14, paddingHorizontal: 14, paddingVertical: 11, color: colors.textPrimary, backgroundColor: colors.background, fontSize: 15 },
  action: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary },
  stopAction: { backgroundColor: colors.error },
  loader: { position: 'absolute', top: 60, right: 20 },
});
