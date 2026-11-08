import { atom } from "jotai";
import type { PriceChannel, PriceFilters } from "@/lib/price.queries";

export interface PriceOption {
  value: string;
  label: string;
}

export interface PriceMarketOptions {
  markets: PriceOption[];
  forms: PriceOption[];
  grades: PriceOption[];
  packages: PriceOption[];
  weights?: PriceOption[];
}

export interface PriceLookupState {
  channel: PriceChannel;
  filters: PriceFilters;
  applied: PriceFilters;
  optionNames: PriceMarketOptions;
  filtersOpen: boolean;
  extraFiltersOpen: boolean;
  displayMode: "pack" | "kg";
}

// Public lookup preferences live only in the current app's Jotai store.
export const priceLookupStateAtom = atom<PriceLookupState | null>(null);
