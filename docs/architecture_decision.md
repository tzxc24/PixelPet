# Architecture decision: B — isolated gateway

Date: 2026-11-05. PixelPet retains its existing FastAPI/SQLite service. Future native xiaozhi WebSocket traffic terminates in a separate gateway or separately deployed upstream server; the gateway calls PixelPet business services. MQTT+UDP is outside V1 scope. This preserves existing storage, API and browser behavior and avoids sharing conflicting routes with another server.

## Source lock and evidence

GitHub API commit lookup returned HTTP 403 (rate limit). Exact refs were therefore resolved with `git ls-remote`, then individual files downloaded by immutable SHA to `tmp/vendor`; no large clone was made.

- Firmware: [78/xiaozhi-esp32 at a73e9a7e266e3196d1368ba46c30bee0d81f0a64](https://github.com/78/xiaozhi-esp32/tree/a73e9a7e266e3196d1368ba46c30bee0d81f0a64).
- Server: [xinnan-tech/xiaozhi-esp32-server at e61f5aee28f1ed7d3bb445d5bfbf5e70452b92fb](https://github.com/xinnan-tech/xiaozhi-esp32-server/tree/e61f5aee28f1ed7d3bb445d5bfbf5e70452b92fb).
- Read firmware README, custom-board guide, WebSocket protocol, websocket_protocol.cc, no_audio_codec.h; server README, Deployment.md, core/connection.py. Local commit metadata records retrieval details.

The [pinned protocol](https://github.com/78/xiaozhi-esp32/blob/a73e9a7e266e3196d1368ba46c30bee0d81f0a64/docs/websocket.md) uses authenticated headers, native hello negotiation, JSON controls and binary Opus. Initial audio parameters include 16kHz mono, typically 60ms; downlink can negotiate 24kHz. Native binary v1 is raw Opus; v2/v3 have headers. These are reference requirements, not capabilities of PixelPet's JSON mock. No audio binary data is accepted by the business endpoint. Native capture/replay, codec negotiation and framing compatibility tests remain BLOCKED_PROTOCOL_INTEGRATION.

The [server deployment guide](https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/e61f5aee28f1ed7d3bb445d5bfbf5e70452b92fb/docs/Deployment.md) describes separate server deployment/configuration and local ASR models; it has not been installed or run here. XiaozhiAdapter explicitly raises an unavailable error rather than fabricating compatibility.

## Current boundary

DONE: typed PixelPet business events, bounded metadata audit, pure FSM/effects, presence/heartbeat, JSON WebSocket mock lifecycle and isolated host core tests.

PARTIAL: board scaffold and protocol integration contract. DONE: ESP-IDF v6.1 native esp32s3 build with guarded physical driver functions and host interlock tests. PARTIAL: native gateway and Opus interoperability are not implemented/validated. HW_PENDING: all actual electrical and radio/audio/display testing.
