import { formatDate } from "@/lib/utils";
import { useMemo } from "react";
import {
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} from "@/components/ui/accordion";

interface ChangelogFrontmatter {
  title: string;
  description?: string;
  date: string;
  version?: string;
  tags?: string[];
}

interface ChangelogModule {
  default: React.ComponentType<{
    components?: Record<string, React.ComponentType<unknown>>;
  }>;
  frontmatter: ChangelogFrontmatter;
}

// Components referenced by JSX inside the .mdx files must be passed in — MDX
// doesn't auto-resolve capitalized tags. Add new ones here as changelogs use them.
const mdxComponents = {
  Accordion,
  AccordionItem,
  AccordionTrigger,
  AccordionContent,
} as unknown as Record<string, React.ComponentType<unknown>>;

// Every .mdx under the repo-root /changelogs dir is a changelog. Add a file, it
// shows up — no registry. Path is relative to this file up to the repo root;
// vite.config's server.fs.allow lets the dev server read above the frontend root.
const modules = import.meta.glob<ChangelogModule>("../../../../changelogs/*.mdx", {
  eager: true,
});

const ChangeLogsPage = () => {
  const sortedChangelogs = useMemo(() => {
    return Object.entries(modules)
      .map(([url, mod]) => ({ url, Body: mod.default, data: mod.frontmatter }))
      .sort(
        (a, b) =>
          new Date(b.data.date).getTime() - new Date(a.data.date).getTime()
      );
  }, []);

  return (
    <div className="min-h-screen bg-background relative">
      {/* Header */}
      <div className="max-w-5xl mx-auto px-6 lg:px-10 pt-6">
        <h1 className="text-3xl font-bold tracking-tight">Changelog</h1>
        <p className="text-muted-foreground mt-2">
          What&apos;s new, improved, and fixed.
        </p>
      </div>

      {/* Timeline */}
      <div className="max-w-5xl mx-auto px-6 lg:px-4 pt-4">
        <div className="relative">
          {sortedChangelogs.map((changelog) => {
            const Body = changelog.Body;
            const formattedDate = formatDate(new Date(changelog.data.date));

            return (
              <div key={changelog.url} className="relative">
                <div className="flex flex-col md:flex-row gap-y-6">
                  <div className="md:w-48 flex-shrink-0">
                    <div className="md:sticky md:top-8 pb-6">
                      <time className="text-sm font-medium text-muted-foreground block mb-3">
                        {formattedDate}
                      </time>

                      {changelog.data.version && (
                        <div className="inline-flex relative z-10 items-center justify-center w-10 h-10 text-foreground border border-border rounded-lg text-sm font-bold">
                          {changelog.data.version}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Right side - Content */}
                  <div className="flex-1 md:pl-8 relative pb-6">
                    {/* Vertical timeline line */}
                    <div className="hidden md:block absolute top-2 left-0 w-px h-full bg-border">
                      {/* Timeline dot */}
                      <div className="hidden md:block absolute -translate-x-1/2 size-3 bg-primary rounded-full z-10" />
                    </div>

                    <div className="space-y-6">
                      <div className="relative z-10 flex flex-col gap-2">
                        <h2 className="text-2xl font-semibold tracking-tight text-balance">
                          {changelog.data.title}
                        </h2>

                        {/* Tags */}
                        {changelog.data.tags &&
                          changelog.data.tags.length > 0 && (
                            <div className="flex flex-wrap gap-2">
                              {changelog.data.tags.map((tag: string) => (
                                <span
                                  key={tag}
                                  className="h-6 w-fit px-2 text-xs font-medium bg-muted text-muted-foreground rounded-full border flex items-center justify-center"
                                >
                                  {tag}
                                </span>
                              ))}
                            </div>
                          )}
                      </div>
                      <div className="prose dark:prose-invert max-w-none prose-headings:scroll-mt-8 prose-headings:font-semibold prose-a:no-underline prose-headings:tracking-tight prose-headings:text-balance prose-p:tracking-tight prose-p:text-balance">
                        <Body components={mdxComponents} />
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default ChangeLogsPage;
