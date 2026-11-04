import Image from "next/image";

export function Logo({
  withSlogan = false,
  className = "",
}: {
  withSlogan?: boolean;
  className?: string;
}) {
  return withSlogan ? (
    <Image
      src="/brand/Pilao_avec_slogan.png"
      alt="Pilao, le pilote de vos appels d'offres"
      width={360}
      height={154}
      priority
      className={className}
    />
  ) : (
    <Image
      src="/brand/Pilao_sans_slogan.png"
      alt="Pilao"
      width={120}
      height={40}
      priority
      className={className}
    />
  );
}
