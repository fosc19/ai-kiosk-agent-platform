/// <reference types="svelte" />
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_TRACE_COLLECTOR_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
