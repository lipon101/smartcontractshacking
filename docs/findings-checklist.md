# Findings Checklist — Blockchain Security Audit Checklist

Source: [Cyfrin Solodit — Blockchain Security Audit Checklist](https://solodit.cyfrin.io/checklist) · aggregated repo: [https://github.com/Cyfrin/audit-checklist](https://github.com/Cyfrin/audit-checklist)

> Partial export of the interactive checklist page (captured 2026-08-03). The live checklist tracks 370 items; this capture contains the 25 items whose Description/Remediation/References were visible. Reference numbers (#1, #2, ...) are placeholders preserved verbatim from the source page. Section headers that were visible without captured items are listed as empty sections — no content is fabricated for them.

**Captured:** 25 items in 11 categories.

## Denial-Of-Service (DoS) Attack

### 1. Is the withdrawal pattern followed to prevent denial of service?

**Description:** To prevent denial of service attacks during withdrawals, it's critical to follow the withdrawal pattern best practices - pull based approach.

**Remediation:** Implement withdrawal pattern best practices to ensure that contract behavior remains predictable and robust against denial of service attacks.

**References:** #1

### 2. Is there a minimum transaction amount enforced?

**Description:** Enforcing a minimum transaction amount can prevent attackers from clogging the network with zero amount or dust transactions.

**Remediation:** Disallow transactions below a certain threshold to maintain efficiency and prevent denial of service through dust spamming.

**References:** #1, #2

### 3. How does the protocol handle tokens with blacklisting functionality?

**Description:** Tokens with blacklisting capabilities, such as USDC, can pose unique risks and challenges to protocols.

**Remediation:** Account for the possibility of blacklisting within token protocols to ensure continued functionality even if certain addresses are blacklisted.

**References:** #1

### 4. Can forcing the protocol to process a queue lead to DOS?

**Description:** Forcing protocols to process queues, like a queue of dust withdrawals, can be exploited to cause a denial of service.

**Remediation:** Design queue processing in a manner that is resilient to spam and cannot be exploited to cause denial of service.

**References:** #1, #2

### 5. What happens with low decimal tokens that might cause DOS?

**Description:** Tokens with low decimals can present issues where the transaction process fails due to rounding to zero amounts.

**Remediation:** Implement logic to handle low decimal tokens in a way that prevents the transaction process from breaking due to insufficient token amounts.

**References:** #1

### 6. Does the protocol handle external contract interactions safely?

**Description:** Protocols must handle interactions with external contracts in a way that does not compromise their functionality if external dependencies fail.

**Remediation:** Ensure robust handling of external contract interactions to maintain protocol integrity regardless of external contract performance.

**References:** #1

## Donation Attack

### 1. Does the protocol rely on `balance` or `balanceOf` instead of internal accounting?

**Description:** Attackers can manipulate the accounting by donating tokens.

**Remediation:** Implement internal accounting instead of relying on `balanceOf` natively.

**References:** #1

## Front-running Attack

### 1. Are "get-or-create" patterns protected against front-running attacks?

**Description:** Functions combining resource creation and interaction (like getOrCreateAndUse) are vulnerable to front-running attacks where attackers can create the resource with different parameters before the victim, potentially manipulating prices or conditions.

**Remediation:** Separate creation and interaction into distinct transactions or implement robust protections (parameter validation, relative references instead of absolute values) to ensure safe operation regardless of creation timing.

**References:** #1, #2

### 2. Are two-transaction actions designed to be safe from frontrunning?

**Description:** Actions that require two separate transactions may be at risk of frontrunning, where an attacker can intervene between the two calls.

**Remediation:** Ensure critical actions that are split across multiple transactions cannot be interfered with by attackers. This can involve checks or locks between the transactions.

**References:** #1

### 3. Can users maliciously cause others' transactions to revert by preempting with dust?

**Description:** Attackers may cause legitimate transactions to fail by front-running with transactions of negligible amounts.

**Remediation:** Implement checks to prevent transactions with non-material amounts from affecting the contract's state or execution flow.

**References:** #1

### 4. Is the protocol using a properly user-bound commit-reveal scheme?

**Description:** Sensitive on-chain actions can be exposed in the mempool, enabling frontrunning and information exploitation. Effective commit-reveal schemes must bind commitments to specific users and transactions.

**Remediation:** Implement a two-phase process where users first commit a hash containing their address and all transaction parameters, then reveal actual actions after the commitment phase ends, preventing frontrunning and information leakage.

**References:** #1, #2

## Griefing Attack

### 1. Is there an external function that relies on states that can be changed by others?

**Description:** Malicious actors can prevent regular user transactions by making a slight change to the on-chain states.

**Remediation:** Ensure normal user actions especially important actions like withdrawal and repayment are not disturbed by other actors.

**References:** #1, #2, #3

### 2. Can the contract operations be manipulated with precise gas limit specifications?

**Description:** Attackers can supply carefully calculated gas amounts to force specific execution paths in the contract, manipulating its behavior in unexpected ways.

**Remediation:** Implement explicit gas checks before critical operations.

**References:** #1, #2, #3

## Miner Attack

### 1. Is block.timestamp used for time-sensitive operations?

**Description:** Miners can manipulate block.timestamp by several seconds, potentially affecting time-dependent contract logic.

**Remediation:** Use block.number instead of timestamps for critical timing operations or ensure manipulation tolerance is acceptable.

**References:** —

### 2. Is the contract using block properties like timestamp or difficulty for randomness generation?

**Description:** Block properties (timestamp, difficulty) and other predictable values should not be used for randomness as they can be influenced or predicted by miners.

**Remediation:** Use a secure randomness source like Chainlink VRF, commit-reveal schemes, or a provably fair randomization mechanism instead.

**References:** #1

### 3. Is contract logic sensitive to transaction ordering?

**Description:** Miners control transaction ordering and can exploit this for front-running, back-running, or sandwich attacks.

**Remediation:** Implement protection by allowing users to specify acceptable results that revert transactions when breached.

**References:** #1

## Price Manipulation Attack

### 1. Is the price calculated by the ratio of token balances?

**Description:** Price can be manipulated via flash loans or donations if it is derived from the ratio of token balances.

**Remediation:** Use the Chainlink oracles for the asset prices.

**References:** #1, #2, #3

### 2. Is the price calculated from DEX liquidity pool spot prices?

**Description:** Spot price readings derived directly from DEX liquidity pools are vulnerable to manipulation through flash loans that can temporarily drain the pools.

**Remediation:** Use TWAP (time-weighted average price) with appropriate time windows based on asset volatility and liquidity, or use reliable oracle solutions.

**References:** #1, #2

## Reentrancy Attack

### 1. Is there any state change after interaction with an external contract?

**Description:** Untrusted external contract calls could callback leading to unexpected results such as multiple withdrawals or out-of-order events.

**Remediation:** Use check-effects-interactions pattern or reentrancy guards.

**References:** #1, #2, #3

### 2. Is there a view function that can return a stale value during interactions?

**Description:** Read-only reentrancy occurs when a view function, called during a reentrant execution, returns inaccurate data because the contract's state is temporarily inconsistent due to an ongoing external call, potentially misleading dependent protocols.

**Remediation:** Apply the Check-Effects-Interactions pattern to prevent inconsistent state, and ensure the reentrancy guard state is not ENTERED for critical view functions to prevent returning stale data.

**References:** #1, #2, #3

## Replay Attack

### 1. Are there protections against replay attacks for failed transactions?

**Description:** Failed transactions can be susceptible to replay attacks if not properly protected.

**Remediation:** Implement nonce-based or other mechanisms to ensure that each transaction can only be executed once, preventing replay attacks, even if the transaction initially failed.

**References:** #1

### 2. Is there protection against replaying signatures on different chains?

**Description:** Signatures that are valid on one blockchain may be replayed on another, leading to potential security breaches.

**Remediation:** Use chain-specific parameters, such as `block.chainid`, or domain separators as defined in EIP-712 to ensure signatures are only valid on the intended chain.

**References:** #1

## Rug Pull

### 1. Can the admin of the protocol pull assets from the protocol?

**Description:** Some protocols grant an admin with a privilege of pulling assets directly from the protocol. In general, if there is an actor that can affect the user funds directly it must be reported.

**Remediation:** Allow access to only the relevant parts of protocol funds, e.g. by tracking fees internally. Forcing a timelock on the admin actions can be another mitigation.

**References:** #1

## Sandwich Attack

### 1. Does the protocol have an explicit slippage protection on user interactions?

**Description:** An attacker can monitor the mempool and puts two transactions before and after the user's transaction. For example, when an attacker spots a large trade, executes their own trade first to manipulate the price, and then profits by closing their position after the user's trade is executed.

**Remediation:** Allow users to specify the minimum output amount and revert the transaction if it is not satisfied.

**References:** #1, #2

## Sybil Attack

### 1. Is there a mechanism depending on the number of users?

**Description:** It is very easy to trigger actions using a lot of alternative addresses on blockchain. Any quorum mechanism or utilization based rewarding system can be vulnerable to sybil attacks.

**Remediation:** Do not rely on the number of users in quorum design.

**References:** #1, #2, #3

## Sections present in the source but not captured in this export

`Attacker's Mindset`, `Basics`, `Centralization Risk`, `Defi`, `External Call`, `Hash / Merkle Tree`, `Heuristics`, `Integrations`, `Low Level`, `Multi-chain/Cross-chain`, `Signature`, `Timelock`, `Token`, `Version Issues`

---

Captured 2026-08-03 from https://solodit.cyfrin.io/checklist. Reference numbers are source-page placeholders.