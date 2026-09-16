import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  experimental: {
    /*
     * Cap static-generation concurrency.
     *
     * Next defaults to one worker per core, which on a 6 GB machine with
     * a browser and an editor open means seven V8 heaps competing for
     * roughly half a gigabyte of headroom -- the build dies with
     * "Zone Allocation failed" partway through page generation rather
     * than failing on anything in the code.
     *
     * Two workers is slower and finishes. Raise it on a bigger machine.
     */
    cpus: 2,
  },
  images: {
    formats: ['image/avif', 'image/webp'],
    // Grid tiles ship q70 — a 300px card does not need q75 of a 1200px source.
    // Next 16 generates ONLY the qualities declared here; an undeclared
    // `quality` prop is silently coerced to the default.
    qualities: [70, 75],
    // Product art is immutable per source file. The Next 16 default is 4h.
    minimumCacheTTL: 2678400,
  },
}

export default nextConfig
