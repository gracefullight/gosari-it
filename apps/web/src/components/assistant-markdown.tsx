import { preprocessMarkdown } from "@gracefullight/markdown";
import { memo, useMemo } from "react";
import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

const COMPONENTS: Components = {
  a: ({ href, children }) =>
    href ? (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex min-h-11 items-center break-all text-primary underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-ring"
      >
        {children}
      </a>
    ) : (
      <span>{children}</span>
    ),
  table: ({ children }) => (
    <div className="max-w-full overflow-x-auto">
      <table className="w-full border-collapse text-left text-base [&_td]:border [&_td]:border-border [&_td]:px-3 [&_td]:py-2 [&_th]:border [&_th]:border-border [&_th]:bg-muted [&_th]:px-3 [&_th]:py-2">
        {children}
      </table>
    </div>
  ),
};
const REMARK_PLUGINS = [remarkGfm];

export const AssistantMarkdown = memo(function AssistantMarkdown({ text }: { text: string }) {
  const markdown = useMemo(
    () => preprocessMarkdown(text, { maxBoldPer100Words: Number.MAX_SAFE_INTEGER }),
    [text]
  );
  return (
    <div className="min-w-0 break-words text-base leading-relaxed [&_p]:whitespace-pre-wrap [&_p+p]:mt-3 [&_strong]:font-semibold [&_h1]:text-xl [&_h2]:text-lg [&_h3]:text-base [&_h4]:text-base [&_h5]:text-base [&_h6]:text-base [&_h1]:font-semibold [&_h2]:font-semibold [&_h3]:font-semibold [&_h4]:font-semibold [&_h5]:font-semibold [&_h6]:font-semibold [&_ul]:list-disc [&_ul]:space-y-1 [&_ul]:pl-6 [&_ol]:list-decimal [&_ol]:space-y-1 [&_ol]:pl-6 [&_li]:whitespace-normal [&_blockquote]:border-l-2 [&_blockquote]:border-border [&_blockquote]:pl-4 [&_pre]:max-w-full [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:bg-muted [&_pre]:p-3 [&_code]:break-words [&_code]:text-base [&_hr]:my-4 [&_hr]:border-border [&_img]:max-w-full">
      <Markdown skipHtml components={COMPONENTS} remarkPlugins={REMARK_PLUGINS}>
        {markdown}
      </Markdown>
    </div>
  );
});
