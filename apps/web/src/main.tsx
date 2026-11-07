import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { NuqsAdapter } from "nuqs/adapters/react";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { AppShell } from "@/app-shell";
import { AppAnalytics } from "@/components/app-analytics";
import { OnboardingProvider } from "@/components/onboarding-guide";
import "@/styles.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
});

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <NuqsAdapter>
          <OnboardingProvider>
            <AppAnalytics />
            <AppShell />
          </OnboardingProvider>
        </NuqsAdapter>
      </QueryClientProvider>
    </StrictMode>
  );
}
