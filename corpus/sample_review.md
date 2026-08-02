# Sample finding — MANUAL REVIEW

**Title:** [L-03] `governanceCapActive` Unconditionally Disables the `emergencyCouncil` Circuit Breaker in `_distributeEnforced()`

**Firm:** Shieldify  ·  **Protocol:** Up  ·  **Impact:** LOW  ·  **Quality:** 0

**Source link:** https://github.com/shieldify-security/audits-portfolio-md/blob/main/Up-Security-Review.md

---


## Severity

Low Risk

## Description

The enforced-cap release logic is meant to have two independently triggerable safety mechanisms: a governance-set cap and an emergencyCouncil-set emergency cap, the latter existing specifically as a fast, independent circuit breaker. In practice, whenever a governance cap is marked active for a given gauge and epoch, the emergency cap is never consulted at all — not in the primary branch that decides the release percentage, and not in the secondary clamp that's supposed to additionally restrict the result. Both paths are structured so that the presence of an active governance cap fully bypasses the emergency-cap check, rather than the two caps being combined (e.g., taking the stricter of the two).

There is no separate function that lets emergencyCouncil clear or override a governance cap entry — only the governor can write to that state. So if a governance cap is on the books for a specific gauge and epoch (which can persist indefinitely once set — see the related expiry-logic finding), and an incident occurs on that exact gauge during that exact epoch, emergencyCouncil calling its emergency-cap function to halt emissions has no effect whatsoever. The release logic will still allow whatever the stale governance cap permits.

## Location of Affected Code

File: [contracts/Voter.sol#L771-L845](https://github.com/prompter-byte/up-contracts/blob/1e5ebbce0a8ae5904224beec6a9fadc7e0fafa89/contracts/Voter.sol#L771-L845)

```solidity
function _distributeEnforced(address _gauge, uint256 _epoch, uint256 _nominal, uint256 _gaugeLeft) internal {
  uint256 alreadyReleased = releasedByGaugeEpoch[_gauge][_epoch];
  uint256 requestedCumulative = alreadyReleased + _nominal;
  ControllerQuote memory quote = _safeQuoteGaugeCap(_gauge, _epoch, requestedCumulative, alreadyReleased);
  bool governanceCapActive = _governanceGaugeCapActive(_gauge, _epoch);
  bool reportUsable = quote.available && quote.status == REPORT_STATUS_VALID;
  uint256 policyAllowed;

  if (governanceCapActive) {
      policyAllowed = (requestedCumulative * governanceGaugeCapBps[_gauge][_epoch]) / MAX_BPS;
  } else if (reportUsable) {
      policyAllowed = quote.allowedCumulativeEmission;
  } else if (_capFallbackAllowed(quote)) {
      if (emergencyGaugeCapActive[_gauge][_epoch]) {
          policyAllowed = (requestedCumulative * emergencyGaugeCapBps[_gauge][_epoch]) / MAX_BPS;
      } else if (defaultGaugeCapActive[_gauge]) {
          policyAllowed = _fallbackPolicyAllowed(
              _gauge,
              _epoch,
              requestedCumulative,
              defaultGaugeCapBps[_gauge],
              quote.status,
              FALLBACK_REASON_DEFAULT_GAUGE_CAP
          );
      } else if (globalFallbackCapActive) {
          policyAllowed = _fallbackPolicyAllowed(
              _gauge,
              _epoch,
              requestedCumulative,
              globalFallbackCapBps,
              quote.status,
              FALLBACK_REASON_GLOBAL_FALLBACK_CAP
          );
      } else {
          policyAllowed = _fallbackPolicyAllowed(
              _gauge,
              _epoch,
              requestedCumulative,
              MAX_BPS,
              quote.status,
              FALLBACK_REASON_FAIL_OPEN_NOMINAL
          );
      }
  }
```

## Impact

It won't let `emergencyCouncil` clear or override a governance cap entry — only the governor can write to that state.

## Recommendation

Have the emergency cap always participate as an additional restriction rather than being skipped whenever a governance cap is active.

## Team Response

Acknowledged.

## [I-01] No Upper Bound on Emission Multiplier

## Severity

Informational Risk

## Description

Both the global multiplier and per-gauge override only validate that the value is non-zero and different from the current value. There is no upper sanity bound. This multiplier scales directly into the emission cap formula in `quoteGaugeCap`. A single governor transaction can set this to an arbitrarily large value, instantly and effectively removing the emission cap for one gauge or the entire protocol. No timelock or multi-step delay is visible within this contract itself.

## Location of Affected Code

File: [contracts/gauge-caps/GaugeCapController.sol#L178-L183](https://github.com/prompter-byte/up-contracts/blob/1e5ebbce0a8ae5904224beec6a9fadc7e0fafa89/contracts/gauge-caps/GaugeCapController.sol#L178-L183)

```solidity
function setMultiplierWad(uint256 _multiplierWad) external onlyGovernor {
    if (_multiplierWad == 0) revert InvalidReport();
    if (multiplierWad == _multiplierWad) revert SameValue();
    multiplierWad = _multiplierWad;
    emit GlobalMultiplierSet(_multiplierWad);
}
```

## Recommendation

Add an explicit hard ceiling constant (e.g., `MAX_MULTIPLIER_WAD`) and enforce `require(_multiplierWad <= MAX_MULTIPLIER_WAD)` in both setters.

## Team Response

Acknowledged.

## [I-02] CLTwapOracle.sol and `Gauge._pendingFees()` Are Unreferenced Dead Code

## Severity

Informational Risk

## Description

Two unrelated pieces of code in this codebase are fully defined but never invoked from anywhere:

`CLTwapOracle.sol` implements an on-chain Uniswap V3 TWAP-based price oracle (adapted TickMath/OracleLibrary logic). It is not imported by any other contract in scope, not referenced by `GaugeCapController.sol` (which is the contract that would plausibly need an on-chain price cross-check), and the only places it's mentioned anywhere in the repository are its own file and the attribution line in NOTICE.md. Verified via a repo-wide search: no other file imports or references it. This is notable because GaugeCapController's gauge-cap valuation is otherwise entirely trust-based (a governor-appointed publisher or signer-quorum submits values with no on-chain sanity check) — `CLTwapOracle` looks like it was built specifically to close that gap and then never wired in.

`Gauge._pendingFees()` (contracts/gauges/Gauge.sol:106-130) is a defined internal function that computes pending fee amounts for the gauge's two underlying tokens. It is never called by any other function in `Gauge.sol`, and it's not exposed as an external/public function either, so there's no way to invoke it at all — internally or externally. Verified via a repo-wide search: `_pendingFees()` has no call sites anywhere in the codebase.

## Location of Affected Code

File: [contracts/gauges/Gauge.sol#L106-L130](https://github.com/prompter-byte/up-contracts/blob/1e5ebbce0a8ae5904224beec6a9fadc7e0fafa89/contracts/gauges/Gauge.sol#L106-L130)

```solidity
function _pendingFees() internal view returns (uint256 pending0, uint256 pending1, address token0, address token1) {
    if (!isPool) {
        return (0, 0, address(0), address(0));
    }

    IPool pool = IPool(stakingToken);
    (token0, token1) = pool.tokens();
    pending0 = fees0 + pool.claimable0(address(this));
    pending1 = fees1 + pool.claimable1(address(this));

    uint256 supplied = IERC20(stakingToken).balanceOf(address(this));
    if (supplied == 0) {
        return (pending0, pending1, token0, token1);
    }

    uint256 delta0 = pool.index0() - pool.supplyIndex0(address(this));
    if (delta0 > 0) {
        pending0 += (supplied * delta0) / PRECISION;
    }

    uint256 delta1 = pool.index1() - pool.supplyIndex1(address(this));
    if (delta1 > 0) {
        pending1 += (supplied * delta1) / PRECISION;
    }
}
```

## Recommendation

- If `CLTwapOracle` was meant to backstop the trust-based gauge-cap valuation pipeline (`GaugeCapController.publishGaugeEpochValue()`), wire it in as a sanity check before launch, or remove it if the integration was deprioritized — shipping it unused is misleading scaffolding that could be mistaken for an active safeguard.

- If `_pendingFees()` was meant to support a fee-accounting feature that didn't make it into this version, either finish wiring it in or remove it — an unreachable, unexposed function serves no purpose and adds audit surface for no benefit.

## Team Response

Acknowledged.

## [I-03] `Voter.reset()` Authorizes Against Raw `msg.sender` Instead of `_msgSender()`, Breaking Meta-tx Calls

## Severity

Informational Risk

## Description

Voter inherits ERC2771Context with a real trusted forwarder. Every other approval-gated function resolves the caller through `_msgSender()`: `vote()`, `depositManaged()`, `withdrawManaged()`, `claimBribes()`, `claimFees()`. `reset()` is the one exception. When called through the trusted forwarder, `msg.sender` inside the contract is the forwarder's address, not the end user, so isApprovedOrOwner checks the forwarder's own (nonexistent) approval and reverts.

## Location of Affected Code

File: [contracts/Voter.sol#L308-L311](https://github.com/prompter-byte/up-contracts/blob/1e5ebbce0a8ae5904224beec6a9fadc7e0fafa89/contracts/Voter.sol#L308-L311)

```solidity
function reset(uint256 _tokenId) external onlyNewEpoch(_tokenId) nonReentrant {
    if (!IVotingEscrow(ve).isApprovedOrOwner(msg.sender, _tokenId)) revert NotApprovedOrOwner();  // contracts/Voter.sol:309 — raw msg.sender
    _reset(_tokenId);
}
```

## Impact

When called through the trusted forwarder, `msg.sender` inside the contract is the forwarder's address, not the end user, so `isApprovedOrOwner()` checks the forwarder's own (nonexistent) approval and reverts.

## Recommendation

Use `_msgSender()` instead of `msg.sender`.

## Team Response

Acknowledged.

## [I-04] Unescaped Token Symbols in On-Chain SVG Allow XML Injection and Broken NFT Metadata

## Severity

Informational Risk

## Description

The `quoteTokenSymbol` and `baseTokenSymbol` are sourced from an `ERC20's symbol()` call. They are used in the `NFTSVG::generateSVG()` function that calls the [`generateTopText()`](https://github.com/prompter-byte/up-slipstream/blob/647f599031d5333ca5d000b57fe9b26ede0dc14a/contracts/periphery/libraries/NFTSVG.sol#L60) function to return the `svg`. The tokens are derived in `NonfungibleTokenPositionDescriptor::tokenURI()` function from the `positionManager.positions`. But the `positionManager` address is a user-supplied address and the function has no access control.

It is the same situation with `CLFactory::createPool()`, where anyone can create a pool with arbitrary tokens. This means that any attacker can deploy a token with a malicious `symbol()` return value and poison the on-chain metadata of every NFT minted against that pool.

## Location of Affected Code

File: [contracts/periphery/libraries/NFTSVG.sol#L60-L86](https://github.com/prompter-byte/up-slipstream/blob/647f599031d5333ca5d000b57fe9b26ede0dc14a/contracts/periphery/libraries/NFTSVG.sol#L60-L86)

```solidity
function generateTopText(
    string memory quoteTokenSymbol,
    string memory baseTokenSymbol,
    uint256 tokenId,
    int24 tickSpacing
) private pure returns (string memory svg) {
    string memory poolId =
        string(abi.encodePacked("CL", tickToString(tickSpacing), "-", quoteTokenSymbol, "/", baseTokenSymbol));
    string memory tokenIdStr = string(abi.encodePacked("ID #", tokenId.toString()));
    string memory id = string(abi.encodePacked(poolId, tokenIdStr));
@>  svg = string(
        abi.encodePacked(
            '<g id="',
            id,
            '">',
            '<text ... ><tspan x="56" y="85.5938">',
            poolId,
            "</tspan></text>",
            ...
        )
    );
}

```

## Impact

A token deployed with `symbol()` returning e.g. `"></g><script>... ` breaks out of the `id="..."` XML attribute and injects arbitrary markup, a symbol containing a bare `<` or `&` produces malformed XML that fails to render entirely. This permanently corrupts or hijacks the on-chain metadata for every NFT holder of that pool/gauge, not just the attacker, a griefing vector against any innocent LP who later stakes a position in that pool.

## Proof of Concept

1. Attacker deploys an ERC20 with `symbol()` returning `X"><image href=x onerror=alert(1)//`.
2. Attacker creates a CL pool pairing this token with a legitimate token.
3. Any NFT minted on that pool calls `generateSVG`, which calls `generateTopText()`, embedding the hostile symbol unescaped into the `id` attribute and `<tspan>` text.
4. The resulting `tokenURI JSON/SVG` is malformed or contains injected markup, breaking rendering in marketplaces or executing injected content in any renderer that doesn't sandbox SVG.

## Recommendation

Escape `", ', <, >`, and `&` in every token-symbol derived string before interpolating it into SVG output (attribute or text-node context), e.g. via a byte-by-byte escaping helper analogous to Uniswap V3's `escapeQuotes`:

```diff
- string memory poolId =
-     string(abi.encodePacked("CL", tickToString(tickSpacing), "-", quoteTokenSymbol, "/", baseTokenSymbol));
+ string memory poolId =
+     string(abi.encodePacked("CL", tickToString(tickSpacing), "-", _escapeXML(quoteTokenSymbol), "/", _escapeXML(baseTokenSymbol)));

```

## Team Response

Fixed.


