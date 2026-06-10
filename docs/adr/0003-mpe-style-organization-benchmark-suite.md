# 使用 MPE-style 多场景组织记忆基准

本项目将组织记忆验证从单一围堵样例扩展为 MPE-style 多场景 benchmark suite，覆盖追捕围堵、协同导航覆盖和接力运输三类协作结构。这个决策避免把组织记忆误写成某个 toy case 的技巧，同时保持零第三方依赖和服务器可复现；代价是当前 suite 是自包含实现，而不是直接依赖 PettingZoo/MPE 包。
