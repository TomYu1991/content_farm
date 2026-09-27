---
title: "如何为个人博客选静态托管：写给不会编程的新手"
description: "面向零基础读者的静态网站托管选择指南：比较 Cloudflare Pages、GitHub Pages、Netlify 等免费托管的部署方式与注意事项，并给出一条从零到上线的具体流程。"
pubDate: "2026-09-27T02:08:28Z"
tags:
- "静态网站"
- "Cloudflare Pages"
- "免费托管"
- "新手建站"
- "个人博客"
slug: "choose-static-hosting-for-personal-blog"
draft: false
ai_assisted: true
model: "deepseek-flash"
prompt_version: "1.0.0"
sources:
- title: "Cloudflare Pages 文档"
  url: "https://developers.cloudflare.com/pages/"
  accessedDate: "2025-06-01T00:00:00Z"
- title: "Cloudflare Pages 平台限制"
  url: "https://developers.cloudflare.com/pages/platform/limits/"
  accessedDate: "2025-06-01T00:00:00Z"
- title: "Cloudflare Pages 直接上传（Direct Upload）指南"
  url: "https://developers.cloudflare.com/pages/get-started/direct-upload/"
  accessedDate: "2025-06-01T00:00:00Z"
- title: "GitHub Pages 文档"
  url: "https://docs.github.com/en/pages"
  accessedDate: "2025-06-01T00:00:00Z"
- title: "GitHub Pages 使用限制"
  url: "https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits"
  accessedDate: "2025-06-01T00:00:00Z"
- title: "Netlify 定价"
  url: "https://www.netlify.com/pricing/"
  accessedDate: "2025-06-01T00:00:00Z"
- title: "Vercel 定价"
  url: "https://vercel.com/pricing"
  accessedDate: "2025-06-01T00:00:00Z"
---
> 这是一篇草稿，面向第一次搭博客、不写代码的读者。文中提到的免费额度、菜单名称和政策都可能变化，动手前请以官方页面为准。

## 先说清楚：静态网站是什么

静态网站就是一堆提前准备好的文件：HTML、CSS、图片、字体。服务器只负责把这些文件原样发给访客的浏览器，不需要数据库，也不需要后台程序一直运行。

对新手来说，这带来几个很实际的好处：

- 便宜，很多平台提供免费托管额度
- 快，没有数据库查询和服务器计算
- 省心，没有后台登录入口，能被攻击的面小

代价也要提前知道：

- 做不了用户登录、在线支付这类需要服务器处理的功能
- 评论、访问统计、站内搜索通常要接第三方服务
- 更新内容靠"改文件、重新上传"，而不是在后台点几下

如果你只是想写文章、放照片、放作品集，静态网站完全够用。

## 选之前先回答四个问题

**1. 你打算怎么把文件传上去？**

这是新手最容易踩坑的地方。托管大致分两类部署方式：

- **拖拽上传**：把文件夹拖进网页里就行，不需要命令行。
- **Git 部署**：平台连上你的代码仓库，你提交一次，它自动重新发布。适合以后想学 Git 的人，但对第一次搭博客的人是多了一层门槛。

**2. 你愿意为什么花钱？**

大多数静态托管的免费额度对个人博客够用，真正要花钱的通常只有一样：你自己的域名。先用平台送的二级域名试水，完全没问题。

**3. 你的读者在哪里？**

如果读者主要在中国大陆，这一点的优先级比"免不免费"更高，下面会单独说。

**4. 以后想换平台，文件带得走吗？**

静态网站的好处就是文件属于你自己。尽量别把内容绑进某个平台的专有格式里，能导出、能重新部署，就随时可以搬家。

## 几个常见的选择（只做定性比较）

具体额度请一定看官方页面，因为这类数字和条款变动很快。

**[Cloudflare Pages](https://developers.cloudflare.com/pages/)**

- 部署方式：既支持连接 Git 仓库，也支持直接上传本地文件夹
- 自带 HTTPS 和免费的 `*.pages.dev` 二级域名，可以绑定自己的域名
- 免费额度对个人博客通常够用，具体限制见[官方限制说明](https://developers.cloudflare.com/pages/platform/limits/)
- 注意：控制台以英文为主，完全零基础的人有一点学习成本

**[GitHub Pages](https://docs.github.com/en/pages)**

- 免费，和代码仓库天然集成
- 适合"顺便想学 Git"的人
- 有仓库大小、流量和构建频率方面的限制，具体数字见[官方文档的限制说明](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)
- 仓库公开与否会影响可用功能，用之前确认一下自己的情况符合哪一条

**Netlify / Vercel**

- 都以部署体验好著称，Netlify 有"把文件夹拖进浏览器就发布"的入口
- 免费额度通常按流量或构建时间计算，个人博客一般够用
- 条款变化较快，以 [Netlify 定价页](https://www.netlify.com/pricing/)和 [Vercel 定价页](https://vercel.com/pricing)为准

**其他**：GitLab Pages、Render、Surge、Neocities 等，思路类似。也有提供在线编辑器或现成模板的服务，但项目是否还在维护需要自己确认。

> 提醒：这些平台在中国大陆的访问速度差异很大，先建一个测试站自己测，别只看评测文章。

## 实操：用 Cloudflare Pages 从零发布一个页面

下面走"不碰命令行"的路线。菜单文字可能已经变过，以[官方文档](https://developers.cloudflare.com/pages/get-started/direct-upload/)为准。

1. **准备文件**：在电脑上新建一个文件夹，里面放一个 `index.html`，内容随便写一句"你好"即可。
2. **注册账号**：到 Cloudflare 官网注册并完成邮箱验证。
3. **创建项目**：在控制台进入 Pages，新建项目，选择直接上传（Direct Upload）那条路径，而不是连接 Git。
4. **上传文件夹**：把刚才那个文件夹拖进去或通过选择器上传。等它处理完，你会拿到一个 `xxx.pages.dev` 的地址。
5. **打开看看**：用电脑和手机各访问一次。如果打不开，先确认 `index.html` 位于文件夹最外层，而不是嵌套在一个子文件夹里。
6. **绑定自己的域名（可选）**：买了域名之后，按官方文档添加自定义域名。如果域名的 DNS 已经托管在 Cloudflare，通常几步就能完成；如果 DNS 在别处（比如域名注册商那里），一般是在那边加一条 CNAME 记录，指向你的 `pages.dev` 地址。
7. **强制 HTTPS**：在设置里打开强制 HTTPS，避免有人用 http 访问时报错。

第 6 步是新手最容易卡住的地方。卡住时不要反复删了重来，先去官方文档对照记录类型和主机名，再检查 DNS 是否已经生效。

## 域名、HTTPS、备案

- **域名**：平台送的二级域名可以一直免费用。想更正式就买个域名，价格因后缀和注册商而不同，通常一年几十到一百多元人民币，具体以注册商页面为准。
- **HTTPS**：主流平台会自动签发并续期证书，你一般不用管。绑定域名后，确认浏览器地址栏是锁形图标。
- **备案**：网站文件放在境外主机上，通常不涉及中国大陆的 ICP 备案。但如果以后改用中国大陆境内的服务器或 CDN，一般就需要备案。这类要求会有调整，办理前请以官方最新说明为准。

## 关于中国大陆的访问速度（说实话部分）

Cloudflare Pages、GitHub Pages、Netlify、Vercel 的节点主要在中国大陆境外，从大陆访问的速度和稳定性会因地区、运营商和时段不同而差别很大。有人很快，有人经常打不开，这两种情况都真实存在，没有哪个平台能保证对所有大陆访客都快。

所以建议：

- 建好测试站后，用手机流量、家里宽带、公司网络分别打开一次
- 如果读者主要在大陆，把图片压小、少用体积大的字体文件，改善会很明显
- 真的在意速度，可以考虑有大陆节点的服务，但那通常要花钱，并可能涉及备案

## 发布前检查清单

- [ ] 平台默认域名能打开
- [ ] 手机能打开，排版没乱
- [ ] 自定义域名能打开，并且是 HTTPS
- [ ] 有一个说得过去的 404 页面
- [ ] 源文件在本地有一份，另外在网盘或 Git 仓库里再存一份
- [ ] 记下你加过的 DNS 记录和参数，换平台时要用
- [ ] 知道在哪里查看自己的免费额度用量

## 怎么选：一句话版本

- 完全不想碰命令行：Cloudflare Pages 的直接上传，或者 Netlify 的拖拽部署
- 想顺便学 Git：GitHub Pages
- 还在犹豫：先用免费二级域名发三篇文章，觉得顺手了再买域名

静态托管的试错成本很低。先用免费托管把站点跑起来，比花一周时间比较参数更有用。
