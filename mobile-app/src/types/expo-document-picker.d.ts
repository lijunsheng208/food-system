declare module 'expo-document-picker' {
  export interface DocumentPickerResult {
    canceled: boolean;
    assets: DocumentPickerAsset[];
  }
  export interface DocumentPickerAsset {
    uri: string;
    name?: string;
    size?: number;
    mimeType?: string;
  }
  export function getDocumentAsync(options?: {
    type?: string[] | string;
    copyToCacheDirectory?: boolean;
  }): Promise<{ canceled: boolean; assets: DocumentPickerAsset[] }>;
}
