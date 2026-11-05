# 发版规则（用户定，长期有效）

## 默认行为：修改 ≠ 发布，修改也不升版本号

每次改完代码（加功能、修 bug、改界面），默认只做这些：

1. 改代码（**APP_VERSION 保持不动**）
2. 上传到服务器 `/opt/qqbot/bridge/bot.py`
3. `sudo systemctl restart qqbot-bridge`（主人的机器人立刻用上新代码）
4. **不**升版本号
5. **不**运行发布脚本
6. **不**更新 `https://xrzs.cloud/updates/latest.json`
7. 部署包可以重新打（用于发给别人），但版本号沿用当前的

→ 结果：主人的机器人已是新代码，但**其他用户的更新源里没有新版本**，他们检查也不会看到更新。

## 只有主人明确说"发布版本 / 发版 / 推送更新"时才发布

发布动作：

1. 升 APP_VERSION（例如 3.3.0 → 3.3.1，由主人指定或按语义）
2. `python3 deploy/make_release.py` 生成剔除观察者的发布版
3. 上传发布版到服务器并重启（主人本地仍保留观察者版本）
4. 生成 `latest.json`（版本、日期、说明、sha256）
5. 重新打包部署包
6. 其它用户点「检查更新」才会看到新版本

## 强制更新

只在主人明确要求时，用 latest.json 的 `min_version` 字段。

## 观察者权限

- 仅主人服务器保留，通过 `enable_viewer_role=1` 开启
- 发布版必须由 `make_release.py` 生成（自动剔除观察者代码）
- 每次发版前校验发布文件中 `viewer/观察者` 出现次数为 0

## 更新源

固定为 `https://xrzs.cloud/updates/latest.json`，用户端不可修改。
