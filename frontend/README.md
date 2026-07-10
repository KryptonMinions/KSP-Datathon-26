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
`src/lib/ask/index.ts` and is driven by two env vars in `.env.local`:

- If `NEXT_PUBLIC_API_URL` is set (e.g. `http://localhost:8000`), the app defaults to
  the **real** backend.
- The backend `/ask` endpoint currently only has dummy logic, so in real mode **every
  query returns "Not enough verified information"** — none of the demo fixture stories
  (antecedents, network graph, MO match, review pack, geospatial map) will render.

To see the demo stories — including the interactive **map** block — force mock mode:

```bash
# .env.local
NEXT_PUBLIC_ASK_SERVICE=mock
```

Then **restart** `npm run dev` (env vars resolve at startup, not on hot-reload). In mock
mode, submit a story's exact query verbatim, e.g.:

> Show all theft FIRs filed within 500 meters of MG Road police station in the last 3 months

> **Note:** This is a temporary workaround until the backend is functional. Once the real
> `/ask` endpoint returns proper responses, remove `NEXT_PUBLIC_ASK_SERVICE=mock` to point
> back at the backend.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
