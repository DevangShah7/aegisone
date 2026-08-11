import Link from "next/link";
import { APP_NAME, APP_TAG, APP_TAGLINE, DEVELOPER_NAME } from "@/lib/branding";

export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col px-6 py-16">
      <header className="flex items-center justify-between">
        <span className="text-sm font-medium tracking-widest text-muted-foreground">
          {APP_NAME.toUpperCase()}
        </span>
        <span className="text-xs text-muted-foreground">{APP_TAG}</span>
      </header>

      <section className="mt-16">
        <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">
          {APP_NAME}
        </h1>
        <p className="mt-4 text-lg text-muted-foreground">{APP_TAGLINE}</p>
        <p className="mt-2 text-sm text-muted-foreground">
          Device owners and authorized operators only. No covert operation.
        </p>

        <div className="mt-10 flex flex-wrap gap-4">
          <Link
            href="/login"
            className="inline-flex h-11 items-center justify-center rounded-md bg-primary px-6 text-sm font-medium text-primary-foreground transition hover:bg-primary/90"
          >
            Log in
          </Link>
          <Link
            href="/register"
            className="inline-flex h-11 items-center justify-center rounded-md border border-border bg-background px-6 text-sm font-medium text-foreground transition hover:bg-accent"
          >
            Create account
          </Link>
        </div>
      </section>

      <footer className="mt-auto pt-16 text-xs text-muted-foreground">
        <p>
          © {new Date().getFullYear()} {APP_NAME}. Developed by{" "}
          <span className="font-medium text-foreground">{DEVELOPER_NAME}</span>.
        </p>
      </footer>
    </main>
  );
}