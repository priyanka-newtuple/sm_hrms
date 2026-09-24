declare module '*.mdx' {
  import type { ComponentType } from 'react';

  export const frontmatter: {
    title: string;
    description?: string;
    date: string;
    version?: string;
    tags?: string[];
  };

  const MDXComponent: ComponentType<{
    components?: Record<string, ComponentType<unknown>>;
  }>;
  export default MDXComponent;
}
