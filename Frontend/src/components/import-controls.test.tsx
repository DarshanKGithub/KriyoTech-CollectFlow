import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ImportControls } from "./import-controls";
import { apiFetch } from "@/lib/api";

vi.mock("@/lib/api", () => ({ apiFetch: vi.fn() }));
vi.mock("@/components/product-dialogs", () => ({ showNotice: vi.fn() }));

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    vi.unstubAllGlobals();
});

describe("CSV import assistant", () => {
    it("previews without saving, then imports only after explicit confirmation", async () => {
        vi.mocked(apiFetch)
            .mockResolvedValueOnce({
                ok: true,
                status: 200,
                json: async () => ({
                    preview: true,
                    accepted_rows: 2,
                    rejected_rows: 0,
                    errors: [],
                    correction_rows: [],
                }),
            } as Response)
            .mockResolvedValueOnce({
                ok: true,
                status: 200,
                json: async () => ({
                    preview: false,
                    accepted_rows: 2,
                    rejected_rows: 0,
                    errors: [],
                    correction_rows: [],
                }),
            } as Response);

        const { container } = render(<ImportControls kind="purchase-orders" />);
        const input = container.querySelector('input[type="file"]');
        expect(input).toBeTruthy();
        fireEvent.change(input as HTMLInputElement, {
            target: { files: [new File(["po csv"], "orders.csv", { type: "text/csv" })] },
        });

        await screen.findByText(/Nothing has been saved yet/);
        expect(apiFetch).toHaveBeenCalledTimes(1);
        expect((vi.mocked(apiFetch).mock.calls[0][1]?.body as FormData).get("preview")).toBe("true");

        fireEvent.click(screen.getByRole("button", { name: "Import 2 valid rows" }));
        await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(2));
        expect((vi.mocked(apiFetch).mock.calls[1][1]?.body as FormData).get("preview")).toBeNull();
        await screen.findByText(/2 rows imported/);
    });

    it("offers a correction CSV for rejected rows", async () => {
        vi.mocked(apiFetch).mockResolvedValueOnce({
            ok: false,
            status: 207,
            json: async () => ({
                preview: true,
                accepted_rows: 0,
                rejected_rows: 1,
                errors: [{ row: 2, message: "Vendor reference is missing" }],
                correction_rows: [{
                    po_number: "PO-1",
                    description: "Part",
                    import_error: "Vendor reference is missing",
                    source_row: 2,
                }],
            }),
        } as Response);
        vi.stubGlobal("URL", {
            createObjectURL: vi.fn(() => "blob:correction"),
            revokeObjectURL: vi.fn(),
        });
        const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);

        const { container } = render(<ImportControls kind="purchase-orders" />);
        const input = container.querySelector('input[type="file"]') as HTMLInputElement;
        fireEvent.change(input, {
            target: { files: [new File(["po csv"], "orders.csv", { type: "text/csv" })] },
        });

        fireEvent.click(await screen.findByText("Download rejected rows with errors"));
        expect(URL.createObjectURL).toHaveBeenCalledOnce();
        expect(click).toHaveBeenCalledOnce();
    });
});
