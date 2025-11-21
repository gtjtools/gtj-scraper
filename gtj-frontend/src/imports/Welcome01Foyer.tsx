import svgPaths from "./svg-kwkb08bm7v";
import imgWelcome01Foyer from "figma:asset/9e39c633d6f91e8de09b845477e5cba869e16182.png";

function LogoFull() {
  return (
    <div className="h-[36px] relative shrink-0 w-[280px]" data-name="logo / full">
      <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 280 36">
        <g id="logo / full">
          <g id="Vector">
            <path d={svgPaths.p62ed600} fill="var(--fill-0, white)" />
            <path d={svgPaths.p38f398f0} fill="var(--fill-0, white)" />
            <path d={svgPaths.p5eab100} fill="var(--fill-0, white)" />
            <path d={svgPaths.p29d03592} fill="var(--fill-0, white)" />
            <path d={svgPaths.p30c9a200} fill="var(--fill-0, white)" />
            <path d={svgPaths.p26f54100} fill="var(--fill-0, white)" />
            <path d={svgPaths.p13a1b400} fill="var(--fill-0, white)" />
            <path d={svgPaths.p3b1ef200} fill="var(--fill-0, white)" />
            <path d={svgPaths.p2cbd1400} fill="var(--fill-0, white)" />
          </g>
        </g>
      </svg>
    </div>
  );
}

function Header() {
  return (
    <div className="relative shrink-0 w-full" data-name="header">
      <div className="size-full">
        <div className="box-border content-stretch flex flex-col gap-[16px] items-start pb-[24px] pt-[48px] px-[24px] relative w-full">
          <LogoFull />
          <div className="css-38o49w flex flex-col font-['Inter:Regular',_sans-serif] font-normal justify-center leading-[0] min-w-full not-italic relative shrink-0 text-[18px] text-white tracking-[-0.27px] w-[min-content]">
            <p className="leading-[24px]">Private skies, verified trust.</p>
          </div>
        </div>
      </div>
    </div>
  );
}

function Text() {
  return (
    <div className="box-border content-stretch flex items-center justify-center px-[4px] py-0 relative shrink-0" data-name="Text">
      <div className="css-bsmfkr flex flex-col font-['Inter:Medium',_sans-serif] font-medium justify-center leading-[0] not-italic relative shrink-0 text-[14px] text-nowrap text-white tracking-[-0.084px]">
        <p className="leading-[20px] whitespace-pre">Create an Account</p>
      </div>
    </div>
  );
}

function BtnNext() {
  return (
    <div className="bg-[#335cff] relative rounded-[10px] shrink-0 w-full" data-name="btn-next">
      <div className="flex flex-row items-center justify-center overflow-clip rounded-[inherit] size-full">
        <div className="box-border content-stretch flex gap-[4px] items-center justify-center p-[10px] relative w-full">
          <Text />
        </div>
      </div>
    </div>
  );
}

function Text1() {
  return (
    <div className="box-border content-stretch flex items-center justify-center px-[4px] py-0 relative shrink-0" data-name="Text">
      <div className="css-bbowul flex flex-col font-['Inter:Medium',_sans-serif] font-medium justify-center leading-[0] not-italic relative shrink-0 text-[#5c5c5c] text-[14px] text-nowrap tracking-[-0.084px]">
        <p className="leading-[20px] whitespace-pre">Sign In</p>
      </div>
    </div>
  );
}

function BtnNext1() {
  return (
    <div className="bg-white relative rounded-[10px] shrink-0 w-full" data-name="btn-next">
      <div className="flex flex-row items-center justify-center overflow-clip rounded-[inherit] size-full">
        <div className="box-border content-stretch flex gap-[4px] items-center justify-center p-[10px] relative w-full">
          <Text1 />
        </div>
      </div>
      <div aria-hidden="true" className="absolute border border-[#ebebeb] border-solid inset-0 pointer-events-none rounded-[10px] shadow-[0px_1px_2px_0px_rgba(10,13,20,0.03)]" />
    </div>
  );
}

function Group() {
  return (
    <div className="relative shrink-0 w-full" data-name="group">
      <div className="size-full">
        <div className="box-border content-stretch flex flex-col gap-[16px] items-start p-[24px] relative w-full">
          <BtnNext />
          <BtnNext1 />
        </div>
      </div>
    </div>
  );
}

function ContentWrapper() {
  return (
    <div className="basis-0 content-stretch flex flex-col grow items-start justify-between min-h-px min-w-px overflow-clip relative shrink-0 w-full" data-name="content-wrapper">
      <Header />
      <Group />
    </div>
  );
}

function ScrollAreaWelcome() {
  return (
    <div className="basis-0 box-border content-stretch flex flex-col grow items-start min-h-px min-w-px overflow-x-clip overflow-y-auto pb-[34px] pt-[62px] px-0 relative shrink-0 w-full" data-name="scroll-area / Welcome">
      <ContentWrapper />
    </div>
  );
}

function Time() {
  return (
    <div className="basis-0 box-border content-stretch flex gap-[10px] grow h-[22px] items-center justify-center min-h-px min-w-px pb-0 pt-[2px] px-0 relative shrink-0" data-name="Time">
      <p className="font-['SF_Pro:Semibold',_sans-serif] font-[590] leading-[22px] relative shrink-0 text-[17px] text-center text-nowrap text-white whitespace-pre" style={{ fontVariationSettings: "'wdth' 100" }}>
        9:41
      </p>
    </div>
  );
}

function Battery() {
  return (
    <div className="h-[13px] relative shrink-0 w-[27.328px]" data-name="Battery">
      <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 28 13">
        <g id="Battery">
          <rect height="12" id="Border" opacity="0.35" rx="3.8" stroke="var(--stroke-0, white)" width="24" x="0.5" y="0.5" />
          <path d={svgPaths.p3bbd9700} fill="var(--fill-0, white)" id="Cap" opacity="0.4" />
          <rect fill="var(--fill-0, white)" height="9" id="Capacity" rx="2.5" width="21" x="2" y="2" />
        </g>
      </svg>
    </div>
  );
}

function Levels() {
  return (
    <div className="basis-0 box-border content-stretch flex gap-[7px] grow h-[22px] items-center justify-center min-h-px min-w-px pb-0 pt-px px-0 relative shrink-0" data-name="Levels">
      <div className="h-[12.226px] relative shrink-0 w-[19.2px]" data-name="Cellular Connection">
        <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 20 13">
          <path clipRule="evenodd" d={svgPaths.p1e09e400} fill="var(--fill-0, white)" fillRule="evenodd" id="Cellular Connection" />
        </svg>
      </div>
      <div className="h-[12.328px] relative shrink-0 w-[17.142px]" data-name="Wifi">
        <svg className="block size-full" fill="none" preserveAspectRatio="none" viewBox="0 0 18 13">
          <path clipRule="evenodd" d={svgPaths.p1fac3f80} fill="var(--fill-0, white)" fillRule="evenodd" id="Wifi" />
        </svg>
      </div>
      <Battery />
    </div>
  );
}

function MobileStatusBar() {
  return (
    <div className="absolute box-border content-stretch flex gap-[154px] items-center justify-center left-0 pb-[19px] pt-[21px] px-[16px] right-0 top-0" data-name="Mobile / Status Bar">
      <Time />
      <Levels />
    </div>
  );
}

function MobileHomeIndicator() {
  return (
    <div className="absolute bottom-0 h-[34px] left-0 right-0" data-name="Mobile / Home Indicator">
      <div className="absolute bottom-[8px] flex h-[5px] items-center justify-center left-1/2 translate-x-[-50%] w-[144px]">
        <div className="flex-none rotate-[180deg] scale-y-[-100%]">
          <div className="bg-white h-[5px] rounded-[100px] w-[144px]" data-name="Home Indicator" />
        </div>
      </div>
    </div>
  );
}

export default function Welcome01Foyer() {
  return (
    <div className="content-stretch flex flex-col gap-[8px] items-start relative size-full" data-name="Welcome / 01 Foyer">
      <div aria-hidden="true" className="absolute inset-0 pointer-events-none">
        <div className="absolute bg-white inset-0" />
        <img alt="" className="absolute max-w-none object-50%-50% object-cover size-full" src={imgWelcome01Foyer} />
        <div className="absolute bg-[rgba(23,23,23,0.1)] inset-0" />
      </div>
      <ScrollAreaWelcome />
      <MobileStatusBar />
      <MobileHomeIndicator />
    </div>
  );
}