"use client";
const brand = {slug:"",name:"KriyoTech Labs",product_name:"KriyoPay",primary_color:"#16734A",support_email:"",is_platform:true};
export const usePartnerBrand = () => brand;
export function ProductName() { return <>KriyoPay</>; }
export function PartnerBrandProvider({children}:{children:React.ReactNode}) { return <>{children}</>; }
