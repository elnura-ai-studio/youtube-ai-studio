import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Privacy Policy — Kelechek AI",
  description:
    "How Kelechek AI accesses, uses, stores and shares data, including data received through YouTube API Services.",
};

const CONTACT_EMAIL = "sabrinaelnura20231985@gmail.com";

const googleScopes = [
  {
    access: "Manage your YouTube account",
    scope: "https://www.googleapis.com/auth/youtube",
    use: "Reads your channel’s ID, title and list of videos, and video details such as titles and thumbnails.",
  },
  {
    access: "Upload YouTube videos",
    scope: "https://www.googleapis.com/auth/youtube.upload",
    use: "Uploads a video to your channel when you request it, or when you have turned on automatic publishing for that channel.",
  },
  {
    access: "View YouTube Analytics reports",
    scope: "https://www.googleapis.com/auth/yt-analytics.readonly",
    use: "Reads performance statistics of your channel and videos: views, watch time, average view duration, audience retention, subscribers gained and lost, aggregated audience statistics by country, and impressions and click-through rate (from YouTube Reporting API reach reports).",
  },
  {
    access: "View monetary YouTube Analytics reports",
    scope: "https://www.googleapis.com/auth/yt-analytics-monetary.readonly",
    use: "Reads revenue statistics of your channel: estimated revenue, estimated ad revenue, gross revenue, CPM and playback-based CPM.",
  },
];

const link = "text-zinc-200 underline underline-offset-2 hover:text-white";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-10">
      <h2 className="text-xl font-semibold mb-3">{title}</h2>
      <div className="space-y-3 text-zinc-300">{children}</div>
    </section>
  );
}

export default function PrivacyPage() {
  return (
    <main className="min-h-screen bg-black text-white p-6">
      <div className="mx-auto w-full max-w-3xl py-6">
        <Link href="/" className="text-zinc-400 hover:text-white">
          ← Kelechek AI
        </Link>

        <h1 className="text-4xl font-bold mt-8 mb-3">Privacy Policy</h1>
        <p className="text-zinc-500">Last updated: 11 October 2026</p>

        <div className="mt-6 rounded-xl border border-zinc-700 bg-zinc-900 p-4 text-zinc-300">
          This policy describes how Kelechek AI currently works. It has not yet been reviewed by a lawyer and may change.
        </div>

        <Section title="1. About this policy">
          <p>
            This policy explains how Kelechek AI (“Kelechek AI”, “we”) accesses, uses, stores and shares information. It covers
            this website and the Kelechek AI application.
          </p>
          <p>
            Kelechek AI is currently a closed version: it is used only by its operator and by invited, adult YouTube channel
            owners. There is no public sign-up and no paid plan.
          </p>
        </Section>

        <Section title="2. YouTube API Services">
          <p>
            Kelechek AI uses <strong className="text-white">YouTube API Services</strong>: the YouTube Data API, the YouTube
            Analytics API and the YouTube Reporting API. By using these features, you also agree to the{" "}
            <a className={link} href="https://www.youtube.com/t/terms" rel="noopener">
              YouTube Terms of Service
            </a>
            . Google’s handling of data is described in the{" "}
            <a className={link} href="https://policies.google.com/privacy" rel="noopener">
              Google Privacy Policy
            </a>
            .
          </p>
        </Section>

        <Section title="3. Information we collect">
          <h3 className="font-semibold text-white">3.1 Account information</h3>
          <ul className="list-disc pl-6 space-y-1">
            <li>Email address and password. The password is never stored in plain text; only a salted hash (PBKDF2-SHA256) is stored.</li>
            <li>Session tokens for signing in. Only a hash of each session token is stored.</li>
          </ul>

          <h3 className="font-semibold text-white pt-2">3.2 Information you enter</h3>
          <ul className="list-disc pl-6 space-y-1">
            <li>Channel settings you enter: niche, content language, audience, goals, style, publishing schedule, AI budget and automation settings.</li>
            <li>Files you upload, such as character reference images.</li>
            <li>Your answers to pre-publish questions (for example, content rights and AI-disclosure declarations) and your review decisions.</li>
          </ul>

          <h3 className="font-semibold text-white pt-2">3.3 Google user data (only for channels you connect)</h3>
          <p>When you connect a YouTube channel with Google sign-in, you grant access to the following scopes. We use them as described:</p>
          <div className="space-y-3">
            {googleScopes.map((s) => (
              <div key={s.scope} className="rounded-xl border border-zinc-700 bg-zinc-900 p-4">
                <p className="font-semibold text-white">{s.access}</p>
                <p className="text-zinc-500 text-sm break-all">{s.scope}</p>
                <p className="mt-2">{s.use}</p>
              </div>
            ))}
          </div>
          <p>
            We also store the OAuth access and refresh tokens that Google issues for each connected channel, so that Kelechek AI
            can act on that channel as described above.
          </p>

          <h3 className="font-semibold text-white pt-2">3.4 Content and usage records</h3>
          <ul className="list-disc pl-6 space-y-1">
            <li>Content generated for you: strategies, scripts, voice-overs, images, video scenes and finished videos.</li>
            <li>Records of AI usage and its estimated cost, used to enforce the AI budget you set.</li>
            <li>Technical logs of requests to the application (for example, which feature was used for which channel).</li>
          </ul>

          <h3 className="font-semibold text-white pt-2">3.5 Cookies</h3>
          <p>
            The application uses one strictly necessary cookie to keep you signed in. It does not use advertising or analytics
            cookies.
          </p>
        </Section>

        <Section title="4. How we use information">
          <p>We use information only to provide and improve the features you see in Kelechek AI:</p>
          <ul className="list-disc pl-6 space-y-1">
            <li>signing you in and keeping each channel visible only to its owner;</li>
            <li>planning and generating content for your channel;</li>
            <li>running pre-publish checks;</li>
            <li>uploading videos to your channel;</li>
            <li>showing you your channel’s performance and revenue statistics, and using performance statistics to suggest content improvements;</li>
            <li>tracking AI usage against your budget.</li>
          </ul>
          <p>We do not sell personal information and do not use it for advertising. Kelechek AI does not train or fine-tune AI models.</p>
        </Section>

        <Section title="5. Sharing with service providers">
          <p>
            To provide its features, Kelechek AI sends the data needed for a specific task to the following providers. Each
            provider processes it under its own terms and policies.
          </p>
          <ul className="list-disc pl-6 space-y-2">
            <li>
              <strong className="text-white">OpenAI</strong> — generates text (strategies, scripts and analysis), images and
              voice-overs. Depending on the feature, it receives: the channel settings you entered; summaries derived from your
              channel’s YouTube data and analytics (for example, a channel profile used for strategy suggestions); your channel’s
              titles and video thumbnails retrieved from YouTube, when analysing a channel’s visual style or characters; images
              you upload; and the script text to be voiced.
            </li>
            <li>
              <strong className="text-white">Google (Gemini API / Veo)</strong> — generates video scenes from text scene
              descriptions when video generation is turned on.
            </li>
            <li>
              <strong className="text-white">Google (YouTube API Services)</strong> — receives the videos and video details that
              you upload through Kelechek AI.
            </li>
          </ul>
          <p>We do not share Google user data with any other parties, except where required by law.</p>
        </Section>

        <Section title="6. Google API Services User Data Policy">
          <p>
            Kelechek AI’s use and transfer of information received from Google APIs to any other app will adhere to the{" "}
            <a className={link} href="https://developers.google.com/terms/api-services-user-data-policy" rel="noopener">
              Google API Services User Data Policy
            </a>
            , including the Limited Use requirements.
          </p>
        </Section>

        <Section title="7. Storage and retention">
          <p>
            Information is stored on infrastructure controlled by the operator of Kelechek AI. Access to a channel’s data is
            restricted to that channel’s owner.
          </p>
          <p>
            Information is kept until you ask us to delete it or until the operator deletes it. Fixed retention periods have not
            yet been set; this section will be updated when they are.
          </p>
        </Section>

        <Section title="8. Your choices">
          <ul className="list-disc pl-6 space-y-2">
            <li>
              <strong className="text-white">Remove Kelechek AI’s access to your Google account</strong> at any time on the{" "}
              <a className={link} href="https://security.google.com/settings/security/permissions" rel="noopener">
                Google security settings page
              </a>
              . After that, Kelechek AI can no longer access your channel. Data already stored stays until it is deleted (see
              below).
            </li>
            <li>
              <strong className="text-white">Ask us to delete your data</strong> by email at the address below. There is no
              self-service deletion in the application yet.
            </li>
            <li>
              <strong className="text-white">Ask questions or make a complaint</strong> about our privacy practices at the
              address below.
            </li>
          </ul>
        </Section>

        <Section title="9. Children">
          <p>
            Kelechek AI is intended for adult YouTube channel owners and is not directed to children. A channel may publish
            content made for children; this does not make the service intended for children.
          </p>
        </Section>

        <Section title="10. Security">
          <p>
            Passwords and session tokens are stored only as hashes, and requests for a channel’s data are checked against the
            channel’s owner. No method of storing or sending data is completely secure.
          </p>
        </Section>

        <Section title="11. Changes to this policy">
          <p>We will update this page when our practices change and change the “Last updated” date above.</p>
        </Section>

        <Section title="12. Contact">
          <p>
            Privacy questions, complaints and deletion requests:{" "}
            <a className={link} href={`mailto:${CONTACT_EMAIL}`}>
              {CONTACT_EMAIL}
            </a>
          </p>
        </Section>

        <footer className="mt-12 border-t border-zinc-800 pt-6 text-sm text-zinc-500 space-y-2">
          <p>
            <Link className={link} href="/terms">
              Terms of Service
            </Link>
          </p>
          <p>Kelechek AI is not affiliated with, endorsed by or sponsored by YouTube or Google. YouTube is a trademark of Google LLC.</p>
        </footer>
      </div>
    </main>
  );
}
