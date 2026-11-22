export default function HomePage() {
  return (
    <main className="mx-auto min-h-screen max-w-5xl px-6 py-10">
      <header className="border-b border-slate-800 pb-5">
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-sky-400">
          Rules Research
        </p>
        <h1 className="mt-2 text-3xl font-semibold text-slate-100">
          Scry-X-AI
        </h1>
      </header>
      <section className="mt-8 grid gap-6 md:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="rounded-md border border-slate-800 bg-slate-950 p-5">
          <label
            htmlFor="rules-question"
            className="text-sm font-medium text-slate-300"
          >
            Rules question
          </label>
          <textarea
            id="rules-question"
            className="mt-3 min-h-32 w-full resize-y rounded-sm border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100 outline-none focus:border-sky-500"
            placeholder="Describe the cards and game state..."
          />
        </div>
        <aside className="rounded-md border border-slate-800 bg-slate-950 p-5">
          <h2 className="text-sm font-semibold text-slate-300">
            Evidence
          </h2>
          <p className="mt-3 text-sm text-slate-500">
            Card text, rulings, and rule citations will appear here.
          </p>
        </aside>
      </section>
    </main>
  );
}
