# Security Policy

ruyijs executes untrusted third-party JavaScript and talks to the network, so we take
security reports seriously.

## Reporting a vulnerability

Please **do not** open a public issue. Report privately through GitHub's
[private vulnerability reporting](https://github.com/martinkeith700/ruyiJS/security/advisories/new).
Include the affected version or commit, the impact, and the minimal steps to reproduce.

We aim to acknowledge reports within 7 days and will coordinate a fix and disclosure with you.

## Scope

In scope: escapes from a page realm into the controller realm or the host, memory-safety
bugs in ruyijs code, the named-pipe RPC and C ABI, TLS/certificate validation in the Necko
transport, and leaks between contexts.

Out of scope: vulnerabilities in upstream SpiderMonkey/Firefox (report them to
[Mozilla](https://www.mozilla.org/security/)), and the expected ability of a page you choose to
run to observe the configured environment.

## Supported versions

Only the latest release receives security fixes.
