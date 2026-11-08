"use client";
import { createContext, useContext } from "react";
export type AdminIdentity = {email:string;name?:string;role:string;is_platform?:boolean};
export const AdminIdentityContext=createContext<AdminIdentity|null>(null);
export const useAdminIdentity=()=>useContext(AdminIdentityContext);
