import { APP_NAME, APP_TAGLINE, APP_VERSION, DEVELOPER_NAME } from "@/lib/branding";

export const metadata = {
  title: "About",
};

export default function AboutPage() {
  return (
    <main className="mx-auto max-w-2xl px-6 py-16">
      <header>
        <span className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
          {APP_NAME}
        </span>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">About</h1>
      </header>

      <section className="mt-8 space-y-6 text-sm leading-relaxed text-muted-foreground">
        <p className="text-base text-foreground">{APP_TAGLINE}.</p>

        <dl className="grid grid-cols-1 gap-x-6 gap-y-4 border-y border-border py-6 sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted-foreground">Product</dt>
            <dd className="text-base text-foreground">{APP_NAME}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted-foreground">Developer</dt>
            <dd className="text-base text-foreground">{DEVELOPER_NAME}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted-foreground">Version</dt>
            <dd className="text-base text-foreground">{APP_VERSION}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted-foreground">Tagline</dt>
            <dd className="text-base text-foreground">Secure. Manage. Protect.</dd>
          </div>
        </dl>

        <p>
          AegisOne is a consent-based platform for device owners and authorized operators.
          It does not function as covert surveillance software. Sensitive operations use the
          platform&rsquo;s official APIs and surface visible system indicators when active.
        </p>
      </section>
    </main>
  );
}