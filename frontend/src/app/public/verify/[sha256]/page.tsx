"use client";

import React from "react";
import { useParams } from "next/navigation";
import { Sha256VerifierPortal } from "@/components/work-orders/sha256-verifier-portal";

export default function PublicVerifySha256Page(): React.JSX.Element {
  const params = useParams<{ sha256: string }>();
  return <Sha256VerifierPortal sha256Hash={params.sha256} />;
}
