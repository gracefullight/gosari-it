import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ApprovalConfirmDialog } from "@/components/approval-confirm-dialog";
import { api } from "@/lib/gosari.api";
import type { Consent, Preview } from "@/lib/gosari.types";

const preview = (id: string): Preview => ({
  preview_id: id,
  preview_hash: `hash-${id}`,
  action: "notebook.create",
  target_id: `target-${id}`,
  target_revision: 0,
  schema_version: "1",
  expires_at: "later",
  display_payload: { activity_text: "합성 수첩" },
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
function mockConsent() {
  return vi.spyOn(api, "consent").mockImplementation(
    async (value) =>
      ({
        consent_id: `consent-${value.preview_id}`,
        preview_id: value.preview_id,
        preview_hash: value.preview_hash,
        action: value.action,
        target_id: value.target_id,
        target_revision: value.target_revision,
      }) as Consent
  );
}
it("retries an ambiguous commit with the same issued consent and recovers the receipt", async () => {
  const consent = mockConsent();
  const commit = vi
    .spyOn(api, "commit")
    .mockRejectedValueOnce(new TypeError("response dropped"))
    .mockResolvedValue({
      state: "committed",
      action_id: "same-action",
      result_id: "same-record",
      resulting_revision: 1,
      safe_error: null,
    });
  const saved = vi.fn();
  const value = preview("first");
  render(<ApprovalConfirmDialog preview={value} onClose={vi.fn()} onCommitted={saved} />);
  fireEvent.click(screen.getByRole("button", { name: "확정" }));
  await screen.findByRole("alert");
  expect(saved).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "확정" }));
  await waitFor(() => expect(saved).toHaveBeenCalledWith("수첩 기록 저장 완료"));
  expect(consent).toHaveBeenCalledTimes(1);
  expect(commit).toHaveBeenCalledTimes(2);
  expect(commit.mock.calls[1]).toEqual(commit.mock.calls[0]);
});
it("never uses an old consent for a different preview", async () => {
  const consent = mockConsent();
  const commit = vi
    .spyOn(api, "commit")
    .mockRejectedValueOnce(new TypeError("response dropped"))
    .mockResolvedValue({
      state: "committed",
      action_id: "next-action",
      result_id: "next-record",
      resulting_revision: 1,
      safe_error: null,
    });
  const saved = vi.fn();
  const { rerender } = render(
    <ApprovalConfirmDialog preview={preview("first")} onClose={vi.fn()} onCommitted={saved} />
  );
  fireEvent.click(screen.getByRole("button", { name: "확정" }));
  await screen.findByRole("alert");
  rerender(
    <ApprovalConfirmDialog preview={preview("different")} onClose={vi.fn()} onCommitted={saved} />
  );
  fireEvent.click(screen.getByRole("button", { name: "확정" }));
  await waitFor(() => expect(saved).toHaveBeenCalled());
  expect(consent).toHaveBeenCalledTimes(2);
  expect(commit.mock.calls[1][1].preview_id).toBe("different");
  expect(commit.mock.calls[1][2].consent_id).toBe("consent-different");
});
