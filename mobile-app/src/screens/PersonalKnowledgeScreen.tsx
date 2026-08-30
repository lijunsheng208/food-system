import React, { useRef, useState } from 'react';
import { ActivityIndicator, Alert, Linking, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import * as DocumentPicker from 'expo-document-picker';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { colors, radius, spacing, typography, shadow } from '../theme';
import { createUploadTicket, uploadDocumentToOSS, completeDocumentUpload, ensurePersonalKnowledgeBase, getDocumentViewTicket, listKnowledgeDocuments, subscribeDocumentStatus, type DocumentStatusSubscription } from '../services/knowledge';

interface LocalDocument { id: number; name: string; size: number; state: 'uploading' | 'pending' | 'processing' | 'completed' | 'failed'; error?: string }

// documentState 将 Logic 文档状态映射为移动端展示状态。
function documentState(status: number): LocalDocument['state'] {
  return status === 2 ? 'processing' : status === 3 ? 'completed' : status === 4 ? 'failed' : 'pending';
}

// PersonalKnowledgeScreen 展示个人知识库并提供文档直传入口。
export default function PersonalKnowledgeScreen() {
  const insets = useSafeAreaInsets();
  const [documents, setDocuments] = useState<LocalDocument[]>([]);
  const [uploadDocument, setUploadDocument] = useState<LocalDocument | null>(null);
  const [uploading, setUploading] = useState(false);
  const pickingRef = useRef(false);
  const statusSubscriptionsRef = useRef(new Map<number, DocumentStatusSubscription>());
  const [knowledgeBaseId, setKnowledgeBaseId] = useState<number | null>(null);

  React.useEffect(() => {
    let active = true;
    // 页面每次挂载都从 Logic 加载当前知识库文档，内存状态不作为历史数据来源。
    void ensurePersonalKnowledgeBase().then(async (baseID) => {
      if (!active) return;
      setKnowledgeBaseId(baseID);
      const items = await listKnowledgeDocuments(baseID);
      if (!active) return;
      setDocuments(items.map((item) => ({ id: item.document_id, name: item.filename, size: item.file_size, state: documentState(item.status) })));
      items.filter((item) => item.status === 1 || item.status === 2).forEach((item) => {
        const subscription = subscribeDocumentStatus(item.document_id, (event) => {
          setDocuments((documents) => documents.map((document) => document.id === event.document_id ? { ...document, state: documentState(event.status) } : document));
          if ([3, 4, 6].includes(event.status)) statusSubscriptionsRef.current.delete(event.document_id);
        });
        statusSubscriptionsRef.current.set(item.document_id, subscription);
      });
    }).catch(() => undefined);
    return () => {
      active = false;
      statusSubscriptionsRef.current.forEach((subscription) => subscription.close());
      statusSubscriptionsRef.current.clear();
    };
  }, []);

  // chooseAndUpload 选择支持的文档并完成申请票据、直传和确认。
  const chooseAndUpload = async () => {
    // 文件选择器是系统级单例；在 Promise 返回前必须锁定入口，避免重复点击触发冲突。
    if (uploading || pickingRef.current || !knowledgeBaseId) return;
    pickingRef.current = true;
    let result: DocumentPicker.DocumentPickerResult;
    try {
      result = await DocumentPicker.getDocumentAsync({ type: ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'text/plain', 'text/markdown'], copyToCacheDirectory: true });
    } catch (error) {
      pickingRef.current = false;
      Alert.alert('选择文件失败', error instanceof Error ? error.message : '请稍后重试');
      return;
    }
    pickingRef.current = false;
    if (result.canceled) return;
    const file = result.assets[0];
    const name = file.name || '未命名文档';
    const contentType = file.mimeType || 'application/octet-stream';
    const fileSize = file.size || 0;
    if (fileSize <= 0 || fileSize > 20 * 1024 * 1024) {
      Alert.alert('无法上传', fileSize > 20 * 1024 * 1024 ? '文件不能超过 20 MB' : '无法读取文件大小');
      return;
    }
    const localID = Date.now();
    setUploadDocument({ id: localID, name, size: fileSize, state: 'uploading' });
    setUploading(true);
    try {
      const ticket = await createUploadTicket(knowledgeBaseId, { filename: name, content_type: contentType, file_size: fileSize });
      await uploadDocumentToOSS(ticket, file.uri, contentType);
      await completeDocumentUpload(ticket.document_id);
      const completedDocument = { id: ticket.document_id, name, size: fileSize, state: 'pending' as const };
      // 待处理文档只显示在上传状态区域，“当前文档”列表仅展示已经完成索引的文档。
      setUploadDocument((item) => item && item.id === localID ? completedDocument : item);
      // 上传确认后订阅 Logic 的最终处理状态，Agent 完成编码时立即刷新当前文档。
      statusSubscriptionsRef.current.get(ticket.document_id)?.close();
      const subscription = subscribeDocumentStatus(ticket.document_id, (event) => {
        const state = documentState(event.status);
        if (state === 'completed') {
          const indexedDocument = { ...completedDocument, state };
          setDocuments((items) => items.some((item) => item.id === event.document_id) ? items.map((item) => item.id === event.document_id ? indexedDocument : item) : [indexedDocument, ...items]);
        }
        setUploadDocument((item) => item?.id === event.document_id ? { ...item, state } : item);
        if ([3, 4, 6].includes(event.status)) statusSubscriptionsRef.current.delete(event.document_id);
      });
      statusSubscriptionsRef.current.set(ticket.document_id, subscription);
    } catch (error) {
      const message = error instanceof Error ? error.message : '上传失败';
      setUploadDocument((item) => item && item.id === localID ? { ...item, state: 'failed', error: message } : item);
      Alert.alert('上传失败', message);
    } finally { setUploading(false); }
  };

  // statusText 将内部文档状态转换为用户可读文本。
  const statusText = (state: LocalDocument['state']) => state === 'uploading' ? '上传中' : state === 'pending' ? '等待处理' : state === 'processing' ? '处理中' : state === 'completed' ? '已完成' : '处理失败';
  // formatSize 将文件字节数格式化为适合移动端显示的容量。
  const formatSize = (size: number) => size > 1024 * 1024 ? `${(size / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(size / 1024))} KB`;

  // viewDocument 获取短期授权地址，并交给系统浏览器或文档查看器打开。
  const viewDocument = async (doc: LocalDocument) => {
    try {
      const ticket = await getDocumentViewTicket(doc.id);
      await Linking.openURL(ticket.view_url);
    } catch (error) {
      Alert.alert('无法查看文档', error instanceof Error ? error.message : '请稍后重试');
    }
  };

  return <View style={[styles.container, { paddingTop: insets.top }]}><ScrollView contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + spacing.xxxl }]}>
    <Text style={styles.title}>个人知识库</Text>
    <Text style={styles.sectionTitle}>当前文档</Text>
    <View style={styles.documentPanel}>
      <ScrollView nestedScrollEnabled showsVerticalScrollIndicator={documents.length > 4} contentContainerStyle={styles.documentList}>
        {documents.length === 0 ? <View style={styles.empty}><Text style={styles.emptyTitle}>暂无文档</Text></View> : documents.map((doc, index) => <View key={doc.id} style={styles.documentRow}><Text style={styles.documentIndex}>{index + 1}.</Text><View style={styles.documentCopy}><View style={styles.documentTitleRow}><Text style={styles.documentName} numberOfLines={1}>{doc.name}</Text><TouchableOpacity style={styles.viewButton} onPress={() => void viewDocument(doc)} accessibilityRole="button" accessibilityLabel={`查看${doc.name}`}><Ionicons name="eye-outline" size={17} color={colors.primary} /><Text style={styles.viewButtonText}>查看</Text></TouchableOpacity></View><Text style={styles.documentMeta}>{formatSize(doc.size)} · {statusText(doc.state)}</Text></View></View>)}
      </ScrollView>
    </View>
    <TouchableOpacity style={styles.uploadButton} onPress={chooseAndUpload} disabled={uploading} activeOpacity={0.8}><Ionicons name={uploading ? 'cloud-upload-outline' : 'add'} size={20} color={colors.textOnPrimary} /><Text style={styles.uploadText}>{uploading ? '上传中…' : '上传知识文档'}</Text>{uploading && <ActivityIndicator color={colors.textOnPrimary} size="small" />}</TouchableOpacity>
    {uploadDocument && <View style={styles.uploadStatus}><Ionicons name="document-text-outline" size={20} color={colors.primary} /><View style={styles.documentCopy}><Text style={styles.documentName} numberOfLines={1}>{uploadDocument.name}</Text><Text style={styles.documentMeta}>{statusText(uploadDocument.state)}</Text>{uploadDocument.error && <Text style={styles.error}>{uploadDocument.error}</Text>}</View>{uploadDocument.state === 'uploading' ? <ActivityIndicator color={colors.primary} /> : <View style={[styles.dot, uploadDocument.state === 'failed' && styles.dotError]} />}</View>}
  </ScrollView></View>;
}

const styles = StyleSheet.create({ container: { flex: 1, backgroundColor: colors.background }, content: { paddingHorizontal: spacing.lg }, title: { ...typography.h1, color: colors.textPrimary, marginTop: spacing.xl, marginBottom: spacing.xxl }, uploadButton: { minHeight: 52, borderRadius: radius.md, backgroundColor: colors.primary, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: spacing.sm, marginTop: spacing.xxl }, uploadText: { ...typography.button, color: colors.textOnPrimary }, sectionTitle: { ...typography.h2, color: colors.textPrimary, marginBottom: spacing.md }, documentPanel: { height: 380, padding: spacing.sm, borderRadius: radius.lg, backgroundColor: 'rgba(255, 255, 255, 0.55)', borderWidth: 1, borderColor: 'rgba(209, 213, 219, 0.7)' }, documentList: { paddingHorizontal: 2, paddingVertical: spacing.xs, gap: spacing.md }, empty: { alignItems: 'center', justifyContent: 'center', minHeight: 340 }, emptyTitle: { ...typography.body, color: colors.textSecondary }, documentRow: { ...shadow.card, minHeight: 72, paddingHorizontal: spacing.md, paddingVertical: spacing.md, flexDirection: 'row', alignItems: 'flex-start', backgroundColor: colors.surface, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border }, documentIndex: { ...typography.body, color: colors.textSecondary, width: 24, paddingTop: 3 }, documentName: { ...typography.body, color: colors.textPrimary, fontWeight: '600', flex: 1 }, documentCopy: { flex: 1, marginLeft: spacing.sm }, documentTitleRow: { minHeight: 30, flexDirection: 'row', alignItems: 'center', gap: spacing.sm }, documentMeta: { ...typography.caption, color: colors.textSecondary, marginTop: 2 }, viewButton: { minWidth: 64, height: 30, paddingHorizontal: spacing.sm, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.primary, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4 }, viewButtonText: { ...typography.caption, color: colors.primary, fontWeight: '600' }, error: { ...typography.caption, color: colors.error, marginTop: 2 }, uploadStatus: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, flexDirection: 'row', alignItems: 'center', marginTop: spacing.md, borderWidth: 1, borderColor: colors.border }, dot: { width: 9, height: 9, borderRadius: 5, backgroundColor: colors.success }, dotError: { backgroundColor: colors.error } });
