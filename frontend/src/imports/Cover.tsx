import svgPaths from "./svg-wtaseyaimz";
import imgCover from "figma:asset/6dce17b8dc8c04f2929c25a8c3d76dcdaeb61620.png";

function LogoSymbol() {
  return (
    <div className="h-[1624.9px] relative w-[3249.8px]" data-name="logo / symbol">
      <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 3250 1625">
        <g id="logo / symbol" opacity="0.39" style={{ mixBlendMode: "overlay" }}>
          <path d={svgPaths.p1c98bb00} fill="var(--fill-0, white)" id="Vector" />
        </g>
      </svg>
    </div>
  );
}

function LogoFull() {
  return (
    <div className="h-[72px] relative shrink-0 w-[560px]" data-name="logo / full">
      <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 560 72">
        <g id="logo / full">
          <g id="Vector">
            <path d={svgPaths.p25eb0100} fill="var(--fill-0, white)" />
            <path d={svgPaths.p2ccaed80} fill="var(--fill-0, white)" />
            <path d={svgPaths.p1dca6000} fill="var(--fill-0, white)" />
            <path d={svgPaths.pe49d200} fill="var(--fill-0, white)" />
            <path d={svgPaths.p308e9300} fill="var(--fill-0, white)" />
            <path d={svgPaths.p2cf65580} fill="var(--fill-0, white)" />
            <path d={svgPaths.p1cdbaf00} fill="var(--fill-0, white)" />
            <path d={svgPaths.p2c7c4a80} fill="var(--fill-0, white)" />
            <path d={svgPaths.p20a58a00} fill="var(--fill-0, white)" />
          </g>
        </g>
      </svg>
    </div>
  );
}

function Container() {
  return (
    <div className="box-border content-stretch flex gap-[8px] items-center justify-center px-[4px] py-0 relative shrink-0" data-name="container">
      <div className="flex flex-col font-['Inter:Bold',_sans-serif] font-bold justify-center leading-[0] not-italic relative shrink-0 text-[#121212] text-[20px] text-nowrap tracking-[-0.4px]">
        <p className="leading-[1.2] whitespace-pre">Version 1</p>
      </div>
    </div>
  );
}

function AnnotationNote() {
  return (
    <div className="bg-white box-border content-stretch flex gap-[4px] items-center p-[12px] relative rounded-[40px] shadow-[0px_0px_2px_0px_rgba(18,18,18,0.2),0px_4px_10px_0px_rgba(18,18,18,0.1)] shrink-0" data-name="Annotation Note">
      <Container />
    </div>
  );
}

function Frame1() {
  return (
    <div className="content-stretch flex flex-col gap-[16px] items-start relative shrink-0">
      <div className="font-['Rethink_Sans:Bold',_sans-serif] font-bold leading-none relative shrink-0 text-[120px] text-nowrap text-white whitespace-pre">
        <p className="mb-0">UI/UX</p>
        <p>Design</p>
      </div>
      <AnnotationNote />
    </div>
  );
}

export default function Cover() {
  return (
    <div className="relative size-full" data-name="Cover">
      <div aria-hidden="true" className="absolute inset-0 pointer-events-none">
        <div className="absolute bg-white inset-0" />
        <div className="absolute inset-0 overflow-hidden">
          <img alt="" className="absolute h-[266.63%] left-0 max-w-none top-[-79.88%] w-[113.49%]" src={imgCover} />
        </div>
      </div>
      <div className="size-full">
        <div className="box-border content-stretch flex flex-col items-start justify-between p-[120px] relative size-full">
          <div className="absolute flex h-[calc(1px*((var(--transform-inner-width)*0.7527390122413635)+(var(--transform-inner-height)*0.6583190560340881)))] items-center justify-center left-[164px] mix-blend-overlay top-[-1857px] w-[calc(1px*((var(--transform-inner-height)*0.7527390122413635)+(var(--transform-inner-width)*0.6583190560340881)))]" style={{ "--transform-inner-width": "3249.78125", "--transform-inner-height": "1624.890625" } as React.CSSProperties}>
            <div className="flex-none rotate-[131.172deg] scale-y-[-100%]">
              <LogoSymbol />
            </div>
          </div>
          <LogoFull />
          <Frame1 />
        </div>
      </div>
    </div>
  );
}