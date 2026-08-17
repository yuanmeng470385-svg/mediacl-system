/**
 * jest 环境准备。
 * AsyncStorage 是原生模块，jest 环境下必须用官方 mock 替换，
 * 否则 apiClient.getToken() 会抛 "NativeModule: AsyncStorage is null"。
 */
jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

// multipart 契约测试需要 FormData；RN jest 环境不保证提供，缺失时给最小实现。
// 注意：Node 18+ 自带 undici FormData，会把 append 的对象值 String() 成 "[object Object]"，
// {uri,name,type} 文件对象 get() 取不回原值 —— 原生存在但行为不符时同样替换。
function formDataPreservesRawObjectValues() {
  try {
    const probe = new global.FormData();
    probe.append('k', { a: 1 });
    const got = probe.get('k');
    return got !== null && typeof got === 'object';
  } catch {
    return false;
  }
}
if (
  typeof global.FormData === 'undefined' ||
  !formDataPreservesRawObjectValues()
) {
  class FormDataPolyfill {
    constructor() {
      this.parts = [];
    }
    append(key, value) {
      this.parts.push({ key, value });
    }
    get(key) {
      const found = this.parts.find((p) => p.key === key);
      return found ? found.value : null;
    }
    getAll(key) {
      return this.parts.filter((p) => p.key === key).map((p) => p.value);
    }
  }
  global.FormData = FormDataPolyfill;
}
