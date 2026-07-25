This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

## Ask service: mock vs. real backend

The Ask page (`/ask`) can talk to either a **mock** service (deterministic fixture
responses, no backend needed) or the **real** backend. The toggle lives in
`src/lib/ask/index.ts` and is driven by env vars in `.env.local`:

- If `NEXT_PUBLIC_API_URL` is set (e.g. `http://localhost:8000`), the app defaults to
  the **real** backend.
- What the real backend actually does depends on the backend's own `ASK_ENGINE`
  setting (see `backend/README.md`): `fixture` serves the same canned demo stories
  as mock mode; `agent` runs the real orchestrator against live Supabase data and
  an LLM — actual answers, not fixtures, and not every block type is wired yet
  (see `E2E_TESTING_GAPS.md` at the repo root for current known gaps, e.g.
  `PackReportBlock`/review-pack summaries).

To force mock mode regardless of the backend (no backend required at all):

```bash
# .env.local
NEXT_PUBLIC_ASK_SERVICE=mock
```

Then **restart** `npm run dev` (env vars resolve at startup, not on hot-reload). In mock
mode, submit a story's exact query verbatim, e.g.:

> Show all theft FIRs filed within 500 meters of MG Road police station in the last 3 months

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
