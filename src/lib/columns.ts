import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { getCollection } from 'astro:content';

const POSTS_DIR = join(process.cwd(), 'src/content/posts');

export interface ColumnInfo {
  /** directory name, used in URLs */
  name: string;
  /** human-readable name from _column.json (falls back to dir name) */
  displayName: string;
  description: string;
  order: number;
  postCount: number;
}

interface ColumnConfig {
  displayName?: string;
  description?: string;
  order?: number;
}

function readColumnConfig(dirName: string): ColumnConfig {
  const cfgPath = join(POSTS_DIR, dirName, '_column.json');
  if (!existsSync(cfgPath)) return {};
  try {
    return JSON.parse(readFileSync(cfgPath, 'utf-8')) as ColumnConfig;
  } catch {
    return {};
  }
}

/**
 * List all columns: every subdirectory of src/content/posts is a column.
 * Metadata comes from an optional _column.json inside the directory.
 */
export async function getColumns(): Promise<ColumnInfo[]> {
  if (!existsSync(POSTS_DIR)) return [];

  const dirs = readdirSync(POSTS_DIR, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => d.name);

  if (dirs.length === 0) return [];

  const posts = await getCollection('posts', ({ data }) => !data.draft);

  return dirs
    .map((dir) => {
      const cfg = readColumnConfig(dir);
      return {
        name: dir,
        displayName: cfg.displayName ?? dir,
        description: cfg.description ?? '',
        order: cfg.order ?? 999,
        postCount: posts.filter((p) => p.id.startsWith(`${dir}/`)).length,
      };
    })
    .sort((a, b) => a.order - b.order || a.name.localeCompare(b.name));
}

/** Display name for a single column (falls back to the directory name). */
export function getColumnName(dirName: string): string {
  return readColumnConfig(dirName).displayName ?? dirName;
}
