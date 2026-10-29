"use client";

import React from "react";
import { useParams } from "next/navigation";
import { Sha256VerifierPortal } from "@/components/work-orders/sha256-verifier-portal";

export default function ShortVerifyHashPage(): React.JSX.Element {
  const params = useParams<{ hash: string }>();
  return <Sha256VerifierPortal sha256Hash={params.hash} />;
}
