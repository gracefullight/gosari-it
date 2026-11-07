import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { PriceCardList } from "@/components/price-card-list";

function markup(sourceUrl?: string) {
  return renderToStaticMarkup(
    <PriceCardList
      cards={[
        {
          channel: "retail",
          product: "<script>globalThis.__price_xss = 1</script>",
          source_url: sourceUrl,
          price_value: 32500,
        },
      ]}
    />
  );
}

describe("price source link safety", () => {
  it.each([
    "javascript:globalThis.__price_xss=1",
    "data:text/html,<script>globalThis.__price_xss=1</script>",
    "file:///private/example",
    "mailto:somebody@example.test",
    "not a URL",
    "https://",
    "//example.test/product",
  ])("omits an unsafe or malformed source link: %s", (url) => {
    const html = markup(url);
    expect(html).not.toContain("<a ");
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
    expect(html).toContain("32,500");
  });

  it.each(["https://www.tamnao.com/product", "http://www.forestinfo.or.kr/"])(
    "keeps a normal provider URL with opener protection: %s",
    (url) => {
      const html = markup(url);
      expect(html).toContain(`href="${url}"`);
      expect(html).toContain('rel="noopener noreferrer"');
      expect(html).not.toContain("<script>");
    }
  );
});
