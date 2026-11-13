# Paper fund ownership and recovery

Paper mode simulates fills; Financial Datasets/x402 and LLM calls can still bill their configured accounts. Tests and CI must clear provider/wallet credentials and use fakes. No merge authorizes a live trading or paid-provider run.

A paper fund now has one cooperative local writer. `tick`, `redo`, `run`, `serve`, deployment, ledger mutations, broker writes and destructive fund deletion use an atomic sibling directory named `.<fund>.writer.lock`. A runner retains ownership throughout its lifetime, including waits: stop it before manually ticking, redoing, resuming or deleting its fund. Nested operations in the owning thread are allowed; other threads/processes receive `FundBusy` before reading trading inputs or mutating the book. Broker instances also reject a book changed since they loaded it.

Read-only ledger construction/replay and the halt control remain available while the runner owns the fund. Halting does not undo a bar already in flight. `stop_runner` submits a token-bound cooperative request; it does not signal a PID read from disk. A successful request means accepted, not stopped. Confirm the runner has exited and its owner lock has disappeared before starting another writer. External SIGINT/SIGTERM handling still stops a runner after its current bar. A legacy runner without owner metadata cannot receive the new cooperative request: identify and stop that known process manually through normal OS controls.

A crash deliberately leaves ownership behind. There is **no automatic stale-lock takeover**, PID-age inference or force-unlock command. Before manual recovery:

1. Identify the fund and retain its book, ledger, control/events, owner metadata and runner logs for diagnosis.
2. Independently establish that no runner, manual tick/redo, UI worker or other writer can still touch it. A PID's existence or absence alone is insufficient; PIDs can be reused.
3. Verify the entire ledger hash chain, reconcile the independent broker book and assess any partial bar/fills. Keep the fund halted while an incomplete session is investigated; do not manufacture a missing ledger event from an assumption.
4. After the owner has reviewed consistency and explicitly allowed recovery, remove only the stale lock directory for that exact fund. Start one controlled writer and verify its resulting book/ledger before restoring unattended operation.

The lock is a local coordination mechanism, not an authenticated user boundary or a distributed lease. Do not claim safety across independently replicated/shared storage without validating that filesystem's atomic directory semantics. Same-user manual file edits or bypassing the public APIs remain outside this cooperative protocol. The ledger/checkpoint hashes detect changed bytes, not an authorized writer or malicious recomputation.
