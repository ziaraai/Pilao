import Image from "next/image";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-8">
      <Image
        src="/brand/Pilao_avec_slogan.png"
        alt="Pilao, le pilote de vos appels d'offres"
        width={480}
        height={205}
        priority
      />
    </main>
  );
}
