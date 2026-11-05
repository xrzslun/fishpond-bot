# 用户分级与权限系统 · 实现方案

> 状态：**已实现（2026-10-27）**。现有账号映射：`admin`、`心如止水` = 超级管理员；`user` = 管理员。


> 目标：后台账号分三级（超级管理员 / 管理员 / 用户），不同角色看到不同菜单、能做不同操作；白名单按"谁添加的"归属；增加登录日志；每级可配置配额。

---

## 一、角色与权限矩阵

| 功能 | 超级管理员 | 管理员 | 用户 |
|---|---|---|---|
| 状态（运行状态/日志） | ✅ | ✅ | ❌ |
| 机器人（人设/模型/语音/休息/设置） | ✅ | ❌ | ❌ |
| 聊天（接话/群聊/频率/关键词/前缀/结束语/表情包/无聊） | ✅ | ✅ | ❌ |
| 名单 → 白名单 | ✅ 全部，可管所有 | ✅ 可见自己添加的（可配置全部） | ✅ 仅自己添加的 |
| 名单 → 超级管理员 | ✅ | ❌ | ❌ |
| 名单 → 黑名单 | ✅ | ❌ | ❌ |
| 账号管理 | ✅ 可建 超管/管理员/用户 | ✅ 仅可建用户 | ❌ |
| 登录日志 | ✅ 全部 | ✅ 自己 + 下属账号 | 仅自己 |
| 设置/更新 | ✅ | ❌ | ❌ |
| 添加白名单配额 | 不限（可设） | 由超管设定 | 由上级设定 |
| 删除白名单 | 任意 | 仅自己添加的 | 仅自己添加的 |

**核心规则**
1. 菜单按角色渲染（前端隐藏 + 后端接口强校验，双重保障）
2. 白名单条目记录 `created_by`，非超管只能删除自己添加的
3. 每级账号可设"最多可添加 N 个群 / N 个 QQ"，超出拒绝
4. 超级管理员可添加超级管理员；管理员只能添加用户
5. 账号可禁用、重置密码

---

## 二、数据库设计

### 1. 账号表（把现有 `admins` 升级为 `accounts`）
```sql
accounts (
  id            INTEGER PRIMARY KEY,
  username      TEXT UNIQUE NOT NULL,
  pass_hash     TEXT NOT NULL,
  role          TEXT NOT NULL CHECK(role IN ('super','admin','user')),
  created_by    INTEGER,           -- 上级账号 id，超管为 NULL
  quota_groups  INTEGER,           -- 最多可添加群数，NULL=不限
  quota_users   INTEGER,           -- 最多可添加 QQ 数，NULL=不限
  disabled      INTEGER DEFAULT 0,
  last_login_at TEXT,
  last_login_ip TEXT,
  created_at    TEXT
)
```

### 2. 登录日志
```sql
login_logs (
  id         INTEGER PRIMARY KEY,
  account_id INTEGER,
  username   TEXT,
  role       TEXT,
  success    INTEGER,   -- 1 成功 0 失败
  ip         TEXT,
  ua         TEXT,
  reason     TEXT,      -- 失败原因
  created_at TEXT
)
```

### 3. 白名单归属
```sql
wl_groups (group_id TEXT PRIMARY KEY, created_by INTEGER, created_at TEXT)
wl_users  (qq       TEXT PRIMARY KEY, created_by INTEGER, created_at TEXT)
```
> 迁移时给现有数据补 `created_by = NULL`（超管可见，普通角色看不到）

---

## 三、登录与会话

- 登录成功后写入 `login_logs`（成功/失败都记，含 IP、UA、时间）
- 会话中保存 `account_id / username / role`
- 新增 `GET /api/me` 返回：角色、菜单权限、配额使用情况
- 所有接口加角色校验（装饰器 `require_role("admin")` 等）；白名单删除额外校验 `created_by`

---

## 四、接口清单（新增/改造）

| 接口 | 方法 | 说明 | 权限 |
|---|---|---|---|
| /api/me | GET | 当前账号信息 + 菜单权限 + 配额 | 登录 |
| /api/accounts | GET | 账号列表 | 超管/管理员（管理员只看自己创建的用户） |
| /api/accounts/create | POST | 新建账号（校验角色可否创建） | 超管/管理员 |
| /api/accounts/update | POST | 改配额/重置密码/禁用 | 上级 |
| /api/accounts/delete | POST | 删除账号 | 上级 |
| /api/login-logs | GET | 登录日志（按角色过滤） | 登录 |
| /api/whitelist | GET | 按角色过滤（超管全部，管理员自己，用户自己） | 登录 |
| /api/whitelist/add | POST | 校验配额 + 记录 created_by | 登录 |
| /api/whitelist/remove | POST | 校验归属（超管可删任意） | 登录 |

---

## 五、前端页面

### 1. 导航按角色渲染
- 超管：全部菜单
- 管理员：`状态 | 聊天 | 名单(只白名单) | 账号管理 | 登录日志 | 退出`
- 用户：`名单(只白名单) | 退出`

### 2. 账号管理页（超管/管理员）
```
账号列表
admin(super)   最近登录 10-27 09:00   配额: 不限    [编辑] [重置密码]
zhang(admin)   最近登录 10-26 20:00   群30/QQ30     [编辑] [禁用] [删除]
li(user)       最近登录 10-25 18:00   群5/QQ5       [编辑] [禁用] [删除]

新建账号：用户名 [ ] 密码 [ ] 角色 [管理员/用户] 配额 群[10] QQ[10] [创建]
```
> 管理员打开时"角色"只有"用户"选项

### 3. 登录日志页
```
时间               账号       角色    结果   IP            设备
2026-10-27 09:00   admin    超管    成功   1.2.3.4       Chrome
2026-10-26 20:01   zhang    管理员  失败   ...           密码错误
```

### 4. 白名单页（按角色）
- 超管：全部条目 + 添加（不限）+ 删除任意
- 管理员/用户：只看自己添加的，显示 `已用 3/10`，删除仅自己的

---

## 六、迁移步骤

1. 建新表、`admins` → `accounts`（现有账号默认：你 = 超管，其余 = 管理员）
2. `wl_groups/wl_users` 加 `created_by`，老数据置 NULL
3. 登录逻辑改为写日志 + 会话带角色
4. 接口加权限校验
5. 前端按角色渲染菜单、账号管理页、登录日志页
6. 测试各角色登录后的菜单和操作

---

## 七、需要你确认的点

1. **现有后台管理员**（3 个）怎么分配角色？你 = 超管，另外两个 = 管理员？
2. **管理员能看到全部白名单，还是只看自己添加的？**（方案默认：只看自己的）
3. **用户/管理员能否修改自己添加的群号？**（方案默认：只能删，改=删了重加）
4. **配额是每个账号独立计算吗？**（方案默认：独立，超管可不限）
5. **登录日志保留多久？**（方案默认：永久，可加"只保留最近 30 天"）
6. **聊天里的"超管 QQ"和后台"超级管理员账号"要不要绑定？**（方案默认：两个独立，聊天超管管机器人行为，后台超管管面板）
