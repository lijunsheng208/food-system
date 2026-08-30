const path = require('path');
const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);

// markdown-it 仍以 Node 核心模块名称引用 punycode，显式映射到已安装的浏览器兼容包。
config.resolver.extraNodeModules = {
  ...config.resolver.extraNodeModules,
  punycode: path.dirname(require.resolve('punycode/package.json')),
};

module.exports = config;
