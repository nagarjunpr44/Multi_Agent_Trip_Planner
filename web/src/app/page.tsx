"use client";

import { Header } from "@/components/Header";
import { Hero } from "@/components/landing/Hero";
import { Destinations, Footer, HowItWorks, YourTrips } from "@/components/landing/Sections";
import { useStartTrip } from "@/lib/useStartTrip";

export default function Home() {
  const { start, starting, error } = useStartTrip();
  return (
    <>
      <Header variant="overlay" onNewTrip={() => start()} />
      <main>
        <Hero onStart={start} starting={starting} error={error} />
        <Destinations onStart={start} />
        <YourTrips />
        <HowItWorks />
      </main>
      <Footer onStart={() => window.scrollTo({ top: 0, behavior: "smooth" })} />
    </>
  );
}
