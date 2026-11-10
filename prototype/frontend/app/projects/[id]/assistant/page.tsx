import AskPanel from '@/components/AskPanel';

export default function AssistantPage({ params }: { params: { id: string } }) {
  return (
    <section className="mx-auto h-[calc(100vh-120px)] max-w-4xl">
      <AskPanel projectId={Number(params.id)} />
    </section>
  );
}
