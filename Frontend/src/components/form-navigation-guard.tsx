"use client";
import { UiBox } from "@/components/product-ui";
import type { FormEvent, ReactNode } from "react";
/** Keep API-backed forms in the single-page app even if a form handler misses preventDefault. */
export function FormNavigationGuard({ children }: {
    children: ReactNode;
}) {
    function preventDocumentNavigation(event: FormEvent<HTMLDivElement>) {
        event.preventDefault();
    }
    return <UiBox onSubmitCapture={preventDocumentNavigation}>{children}</UiBox>;
}
