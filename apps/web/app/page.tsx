"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getSupabase, supabaseConfigured } from "@/lib/supabase";

export default function Home() {
  const router = useRouter();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (!supabaseConfigured()) { setChecked(true); return; }
    getSupabase().auth.getSession().then(({ data }) => {
      router.replace(data.session ? "/dashboard" : "/login");
      setChecked(true);
    });
  }, [router]);

  if (!supabaseConfigured()) {
    return (
      <main className="container">
        <div className="card">
          <h1>God Mode AI Software Factory</h1>
          <p className="error">Supabase is not configured for the web app.</p>
          <p className="muted">Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY, then rebuild.</p>
        </div>
      </main>
    );
  }
  return <main className="container"><p className="muted">{checked ? "Redirecting..." : "Loading..."}</p></main>;
}
