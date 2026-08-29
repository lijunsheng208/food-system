import React, { useRef, useState } from 'react';
import { ActivityIndicator, Alert, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import * as DocumentPicker from 'expo-document-picker';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { colors, radius, spacing, typography } from '../theme';
import { createUploadTicket, uploadDocumentToOSS, completeDocumentUpload, ensurePersonalKnowledgeBase } from '../services/knowledge';

interface LocalDocument { id: number; name: string; size: number; state: 'uploading' | 'pending' | 'failed'; error?: string }

// PersonalKnowledgeScreen 展示个人知识库并提供文档直传入口。
export default function PersonalKnowledgeScreen() {
  const insets = useSafeAreaInsets();
  const [documents, setDocuments] = useState<LocalDocument[]>([]);
  const [uploadDocument, setUploadDocument] = useState<LocalDocument | null>(null);
  const [uploading, setUploading] = useState(false);
  const pickingRef = useRef(false);
  const [knowledgeBaseId, setKnowledgeBaseId] = useState<number | null>(null);

  React.useEffect(() => { ensurePersonalKnowledgeBase().then(setKnowledgeBaseId).catch(() => undefined); }, []);

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
      setUploadDocument((item) => item && item.id === localID ? { ...item, id: ticket.document_id, state: 'pending' } : item);
    } catch (error) {
      const message = error instanceof Error ? error.message : '上传失败';
      setUploadDocument((item) => item && item.id === localID ? { ...item, state: 'failed', error: message } : item);
      Alert.alert('上传失败', message);
    } finally { setUploading(false); }
  };

  const statusText = (state: LocalDocument['state']) => state === 'uploading' ? '上传中' : state === 'pending' ? '等待处理' : '上传失败';
  const formatSize = (size: number) => size > 1024 * 1024 ? `${(size / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(size / 1024))} KB`;

  return <View style={[styles.container, { paddingTop: insets.top }]}><ScrollView contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + spacing.xxxl }]}>
    <Text style={styles.title}>个人知识库</Text>
    <Text style={styles.sectionTitle}>当前文档</Text>
    <View style={styles.documentPanel}>
      <ScrollView nestedScrollEnabled showsVerticalScrollIndicator={documents.length > 4}>
        {documents.length === 0 ? <View style={styles.empty}><Text style={styles.emptyTitle}>暂无文档</Text></View> : documents.map((doc) => <View key={doc.id} style={styles.documentRow}><Ionicons name="document-text-outline" size={22} color={colors.primary} /><Text style={styles.documentName} numberOfLines={1}>{doc.name}</Text></View>)}
      </ScrollView>
    </View>
    <TouchableOpacity style={styles.uploadButton} onPress={chooseAndUpload} disabled={uploading} activeOpacity={0.8}><Ionicons name={uploading ? 'cloud-upload-outline' : 'add'} size={20} color={colors.textOnPrimary} /><Text style={styles.uploadText}>{uploading ? '上传中…' : '上传知识文档'}</Text>{uploading && <ActivityIndicator color={colors.textOnPrimary} size="small" />}</TouchableOpacity>
    {uploadDocument && <View style={styles.uploadStatus}><Ionicons name="document-text-outline" size={20} color={colors.primary} /><View style={styles.documentCopy}><Text style={styles.documentName} numberOfLines={1}>{uploadDocument.name}</Text><Text style={styles.documentMeta}>{statusText(uploadDocument.state)}</Text>{uploadDocument.error && <Text style={styles.error}>{uploadDocument.error}</Text>}</View>{uploadDocument.state === 'uploading' ? <ActivityIndicator color={colors.primary} /> : <View style={[styles.dot, uploadDocument.state === 'failed' && styles.dotError]} />}</View>}
  </ScrollView></View>;
}

const styles = StyleSheet.create({ container: { flex: 1, backgroundColor: colors.background }, content: { paddingHorizontal: spacing.lg }, title: { ...typography.h1, color: colors.textPrimary, marginTop: spacing.xl, marginBottom: spacing.xxl }, uploadButton: { minHeight: 52, borderRadius: radius.md, backgroundColor: colors.primary, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: spacing.sm, marginTop: spacing.xxl }, uploadText: { ...typography.button, color: colors.textOnPrimary }, sectionTitle: { ...typography.h2, color: colors.textPrimary, marginBottom: spacing.md }, documentPanel: { height: 260, backgroundColor: colors.surface, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, overflow: 'hidden' }, empty: { alignItems: 'center', justifyContent: 'center', minHeight: 258 }, emptyTitle: { ...typography.body, color: colors.textSecondary }, documentRow: { minHeight: 54, paddingHorizontal: spacing.md, flexDirection: 'row', alignItems: 'center', borderBottomWidth: 1, borderBottomColor: colors.border }, documentName: { ...typography.body, color: colors.textPrimary, fontWeight: '600', flex: 1, marginLeft: spacing.md }, documentCopy: { flex: 1, marginLeft: spacing.md }, documentMeta: { ...typography.caption, color: colors.textSecondary, marginTop: 2 }, error: { ...typography.caption, color: colors.error, marginTop: 2 }, uploadStatus: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, flexDirection: 'row', alignItems: 'center', marginTop: spacing.md, borderWidth: 1, borderColor: colors.border }, dot: { width: 9, height: 9, borderRadius: 5, backgroundColor: colors.success }, dotError: { backgroundColor: colors.error } });
