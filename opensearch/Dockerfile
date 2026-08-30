FROM opensearchproject/opensearch:2.19.1

# 安装与 OpenSearch 2.19.1 匹配的 IK Analyzer。
RUN /usr/share/opensearch/bin/opensearch-plugin install --batch \
    https://get.infini.cloud/opensearch/analysis-ik/2.19.1

# 自定义词典必须放在 IK 插件约定目录，并随镜像固化，避免容器重建后丢失。
COPY config/IKAnalyzer.cfg.xml /usr/share/opensearch/config/analysis-ik/IKAnalyzer.cfg.xml
COPY config/familyos.dic /usr/share/opensearch/config/analysis-ik/familyos.dic
COPY config/stopword.dic /usr/share/opensearch/config/analysis-ik/stopword.dic
