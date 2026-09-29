import { useEffect, useState, type FormEvent } from "react";
import { ArrowRight, Plane } from "lucide-react";

import travelBg from "@/skins/hrms/assets/travel_bg.png";
import { useRequireSignIn } from "@/skins/hrms/auth/useRequireSignIn";
import { Button } from "@/skins/hrms/components/Button";
import { Field, Select, TextArea, TextInput } from "@/skins/hrms/components/Form";
import { PublicContent, PublicHero, PublicPageLayout, SignInToActNotice } from "@/skins/hrms/components/PublicPageLayout";

const TRIP_TYPES = ["Client visit", "Inter-office", "Training", "Conference"] as const;
const NEXT = "/travel-request";

export function TravelRequestPage() {
  const { user, loading, requireSignIn } = useRequireSignIn(NEXT);
  const [tripType, setTripType] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);

  useEffect(() => {
    if (!user) return;
    setFullName((current) => current || user.full_name);
    setEmail((current) => current || user.email);
  }, [user]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!requireSignIn()) return;
    setSubmitted(true);
  }

  return (
    <PublicPageLayout>
      <PublicHero
        image={travelBg}
        imageClass="top-[-4%] left-[18%] h-[135%] w-[155%] object-left-top"
        overlayClass="bg-gradient-to-r from-[#F8F4EF] via-[#F8F4EF]/80 via-[28%] to-transparent to-[52%]"
        kicker="Travel"
        title="Travel Request"
        accent="Plan the trip. We'll take it from there."
        blurb="Request client visits, inter-office travel, or training trips. Share the plan and your manager and Finance will review it."
      />

      <PublicContent>
        <form
          id="travel-form"
          noValidate={!user}
          onSubmit={handleSubmit}
          className="rounded-card bg-white p-6 shadow-lg shadow-gray-900/5 sm:p-8"
        >
          <div className="mb-6 flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-full bg-cobalt/10 text-cobalt">
              <Plane size={18} />
            </span>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">Request travel</h2>
              <p className="text-sm font-light text-gray-600">Share the itinerary and we&apos;ll take it from there.</p>
            </div>
          </div>
          {!user && !loading && (
            <div className="mb-4">
              <SignInToActNotice action="submit a travel request" />
            </div>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Full Name *">
              <TextInput
                name="fullName"
                required
                placeholder="Enter full name"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
              />
            </Field>
            <Field label="Work Email *">
              <TextInput
                name="email"
                type="email"
                required
                placeholder="first.last@newtuple.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </Field>
            <Field label="From *">
              <TextInput name="from" required placeholder="Bengaluru" />
            </Field>
            <Field label="To *">
              <TextInput name="to" required placeholder="Pune / client city" />
            </Field>
            <Field label="Start date *">
              <TextInput name="startDate" type="date" required />
            </Field>
            <Field label="End date *">
              <TextInput name="endDate" type="date" required />
            </Field>
            <Field label="Trip type *">
              <Select name="tripType" required value={tripType} onChange={(e) => setTripType(e.target.value)}>
                <option value="">Select a trip type</option>
                {TRIP_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </Select>
            </Field>
            <div className="sm:col-span-2">
              <Field label="Purpose *">
                <TextArea name="purpose" required placeholder="Client workshop, office week, training…" />
              </Field>
            </div>
          </div>
          {submitted && (
            <p className="mt-4 text-sm font-medium text-success">
              Thanks — your travel request was captured. Your manager will follow up from here.
            </p>
          )}
          {user || loading ? (
            <Button type="submit" className="mt-6">
              Submit request <ArrowRight size={16} />
            </Button>
          ) : (
            <Button type="button" className="mt-6" onClick={() => requireSignIn()}>
              Sign in to submit <ArrowRight size={16} />
            </Button>
          )}
        </form>
      </PublicContent>
    </PublicPageLayout>
  );
}
