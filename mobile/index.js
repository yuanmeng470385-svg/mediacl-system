/**
 * MedAgent 移动端入口
 * 注意：App 组件在 src/App.tsx（非模板默认的根 App.tsx）
 */
import {AppRegistry} from 'react-native';
import App from './src/App';
import {name as appName} from './app.json';

AppRegistry.registerComponent(appName, () => App);
