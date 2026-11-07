import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { AssistantMarkdown } from "@/components/assistant-markdown";

afterEach(cleanup);

it("renders Korean emphasis through the actual preprocessing library and updates streamed text", () => {
  const view = render(<AssistantMarkdown text="** 서귀포가 1위 **입니다." />);
  expect(screen.getByText("서귀포가 1위").tagName).toBe("STRONG");
  view.rerender(<AssistantMarkdown text={'**"서귀포"**가 1위입니다.\n\n- 맑음\n- 강수확률 0%'} />);
  expect(screen.getByText("서귀포").tagName).toBe("STRONG");
  expect(screen.getAllByRole("listitem")).toHaveLength(2);
});

it("renders GFM tables and preserves literal markdown in code", () => {
  const { container } = render(
    <AssistantMarkdown
      text={"| 지역 | 기온 |\n| --- | --- |\n| 서귀포 | 18℃ |\n\n`**강조 아님**`"}
    />
  );
  expect(screen.getByRole("columnheader", { name: "지역" })).toBeTruthy();
  expect(screen.getByRole("cell", { name: "18℃" })).toBeTruthy();
  expect(container.querySelector("code")?.textContent).toBe("**강조 아님**");
});

it("drops raw HTML and unsafe link protocols without enabling HTML execution", () => {
  const { container } = render(
    <AssistantMarkdown
      text={
        '<script>alert("xss")</script>\n\n<img src=x onerror=alert(1)>\n\n[위험](javascript:alert%281%29) [공식](https://example.com)'
      }
    />
  );
  expect(container.querySelector("script")).toBeNull();
  expect(container.querySelector("img")).toBeNull();
  expect(screen.queryByRole("link", { name: "위험" })).toBeNull();
  const link = screen.getByRole("link", { name: "공식" });
  expect(link.getAttribute("href")).toBe("https://example.com");
  expect(link.getAttribute("rel")).toBe("noopener noreferrer");
});
