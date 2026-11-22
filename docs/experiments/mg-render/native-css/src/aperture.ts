// Keep the source timecode visible while the right edge breathes.
export function aperture(frame:number) {
  const edge=79+16*Math.sin(frame/13);
  return {clipPath:`polygon(0 0,100% 0,${edge}% 100%,0 100%)`,
    maskImage:`linear-gradient(105deg, black 48%, rgba(0,0,0,.25) ${edge}%, transparent)`};
}
