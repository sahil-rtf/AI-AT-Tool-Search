import { NextResponse } from "next/server";
import { getJob } from "@/lib/discovery-pipeline";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  
  const job = getJob(id);

  if (!job) {
    return NextResponse.json(
      { error: "Job not found" },
      { status: 404 }
    );
  }

  return NextResponse.json(job);
}
