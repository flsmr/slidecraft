<!-- Running footer: date · author · page. Rendered in-flow at the bottom of the
     content layouts (just beneath the source/citation line), NOT as a global
     layer (Slidev mounts global-bottom in a 0x0 wrapper, which collapses an
     absolutely-positioned footer). Template-only: $slidev / $frontmatter / $page
     / $nav are auto-injected into every component, so we must not re-declare them
     in a <script> block. Author and date come from deck headmatter, with a
     per-slide frontmatter override; page number is this slide's own ($page). Set
     `footer: false` in a slide's frontmatter to suppress it. -->
<template>
  <div v-if="$frontmatter?.footer !== false" class="gen-footer">
    <div class="gen-footer__meta">
      <span v-if="$frontmatter?.date || $slidev.configs.date" class="gen-footer__date">
        {{ $frontmatter?.date || $slidev.configs.date }}
      </span>
      <span
        v-if="($frontmatter?.date || $slidev.configs.date) && ($frontmatter?.author || $slidev.configs.author)"
        class="gen-footer__dot"
      >·</span>
      <span v-if="$frontmatter?.author || $slidev.configs.author" class="gen-footer__author">
        {{ $frontmatter?.author || $slidev.configs.author }}
      </span>
    </div>
    <div class="gen-footer__page">{{ $page }} / {{ $nav.total }}</div>
  </div>
</template>
