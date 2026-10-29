"use client";

import React from "react";
import { useParams } from "next/navigation";
import { PublicQuotePortal } from "@/components/quotes/public-quote-portal";

export default function ShortPublicQuotePage(): React.JSX.Element {
  const params = useParams<{ token: string }>();
  return <PublicQuotePortal publicToken={params.token} />;
}
