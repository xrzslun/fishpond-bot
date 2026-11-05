你是接手 FishPond QQ 机器人项目的助手。请先完整阅读：

/root/Documents/deepseek-harness/default-workspace/qq-deepseek-bot/HANDOFF.md

读完后再开始操作，不要凭记忆猜项目状态。

## 项目位置

- 源码：/root/Documents/deepseek-harness/default-workspace/qq-deepseek-bot
- 主文件：bridge/bot_admin.py
- 发布产物：deploy/files/bridge/bot.py
- 服务器：ubuntu@43.132.175.12（密码/密钥不在文档里，向用户要或使用已有 SSH 配置）
- 后台：https://xrzs.cloud/xrzs/bot/QQbot/
- 机器人 QQ：1571154120

## 必须遵守

1. 用户明确说“发版/发布”才允许 bump 版本和发布；不要自动发。
2. 观察者角色永不出现在发布版；make_release.py 必须保持 VIEWER_FEATURE=False。
3. 记忆功能保留发布，不要关闭。
4. 发布包不能包含数据库、密码、个人后台路径、统计后台地址。
5. 改动前先备份 bot.py 和 data.db。
6. 所有回复使用中文。

## 当前状态（2026-10-29）

- 线上版本：3.5.5
- 更新源：3.5.5，min_version=3.5.5
- app_version：3.5.5
- 服务器运行正常，QQ 在线
- 数据库 memories 约 816 条，记忆开启
- 生图已开启：模型 Qwen/Qwen-Image，25 步，每日 5 张，提示词优化开启
- 3.5.5 已有半强制更新：顶部横幅、写操作 426、悬浮更新按钮、失败 QQ 通知并保留旧版
- 安装包/更新包地址和 SHA 以 https://xrzs.cloud/updates/latest.json 和 /dl/latest.json 为准

## 已完成但尚未发布（准备进 3.5.6）

1. 生图完整功能：@机器人 画图/画一只猫，base64 发图
2. 生图模型下拉带价格/优势：Turbo 0.1、Z-Image 0.3、Qwen 0.3、Kolors 免费
3. 生图提示词优化：自动改写成画面描述
4. 生图注入：AI 人设/自画像外观、用户记忆、黑话词库
5. 问“你居住环境/你吃什么”时，先让 AI 按人设自述画面，再生成
6. 生图测试支持自定义提示词并在后台页面展示图片
7. 黑话词库批量勾选删除
8. 3.5.5 半强制更新 + 更新失败通知

## 待办

- 检查 3.5.5 升级分布（stats.db），确认后发 3.5.6
- 发 3.5.6 时把 latest.json 的 min_version 设为 3.5.6，让 426 真正对 3.5.5 用户生效
- 更新说明写清：半强制、生图、黑话批量删除、失败通知
- 发布后验证 /updates/latest.json、/dl/latest.json、SHA
- 原会话有一个 48 小时提醒（约 2026-10-30 20:13 上海时间）检查升级率，新会话没有这个定时器，需要手动记

## 已知问题

- QQ 会被腾讯踢下线，需要重新扫码，代码只能重连
- 性别感知多数返回 unknown，不要强行猜
- Kolors 复杂构图弱，Qwen-Image 更强但慢/贵
- 生图依赖硅基流动 API 和余额
- 音乐卡片依赖 NapCat 签名服务
- 更新只校验 SHA256，没有签名
- 没有自动化测试，改完必须手工验证关键链路

## 接手第一步

1. 读 HANDOFF.md
2. 检查服务器状态：
   systemctl is-active qqbot-bridge
   curl -s https://xrzs.cloud/updates/latest.json
3. 向用户确认这次要做什么，不要直接发版
