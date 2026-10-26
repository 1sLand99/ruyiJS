# Expedia TAAP 登入

[`expedia.py`](expedia.py) 在 ruyijs+necko 原生环境里打开 Expedia 旅行社门户（TAAP）的登入页，
让页面自己的 React SPA 完成设备指纹（iovation / iesnare）、Arkose FunCaptcha 与登入请求；
脚本只负责导航、在页面自己的表单里填邮箱/密码并点击「登入」。

```powershell
python .\examples\expedia-taap\expedia.py
python .\examples\expedia-taap\expedia.py --proxy http://127.0.0.1:7890 --output expedia.json
python .\examples\expedia-taap\expedia.py --direct
```

## 流程

与 Firefox trace `jscall-detail-desktop-20261025-134004` 逐步一致：

1. `GET /taap/signin` → React SPA 分包（bernie/core/graphql/vendor/app …）加载、渲染登入表单；
   iovation `iesnare` 脚本生成设备画像。
2. `POST /taap/identity/api/v1/pre-auth {email}` → `{"data_exchange_blob":""}`。
3. Arkose FunCaptcha `POST /fc/gt2/public_key/<pk>` → token 带 `sup=1`（抑制模式，无需可视拼图）。
4. `POST /egcs/v2/collect` → 204（点击流 `sign_in.submitted`）。
5. `POST /taap/identity/api/v1/sign-in {email,password,challengeResponse:{arkoseToken…}}` → **202**。
6. `GET /` → **303** → `GET /account-not-associated` → 200，顶层导航落在该页，标题 *Account Not Associated*。

第 6 步是 trace 的业务终态：服务器接受了凭据与 Arkose token，但示例账号未关联 TAAP 代理身份，
因此落到 account-not-associated。这与 Firefox 抓包逐字一致。

## 判定

脚本**不**替换任何浏览器 API、不注入 cookie、不拼 Arkose token、不伪造设备 blob——
这些全部由页面脚本在 ruyijs 环境中算出，necko 负责真实 TLS 与 cookie。

退出码 0（`passed: true`）要求：`pre-auth` 200、Arkose `public_key` 200、`collect` 204、
`sign-in` 202、最终 `/account-not-associated` 200 且顶层 URL 落在该页，并且全程没有页面脚本异常。
