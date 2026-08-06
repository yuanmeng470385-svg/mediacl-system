/**
 * jest 环境准备。
 * AsyncStorage 是原生模块，jest 环境下必须用官方 mock 替换，
 * 否则 apiClient.getToken() 会抛 "NativeModule: AsyncStorage is null"。
 */
jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);
