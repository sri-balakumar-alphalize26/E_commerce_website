/**
 * The type boundary around the vendored sign-in design.
 *
 * SignIn.jsx stays untyped JavaScript, as Home.jsx does -- both are vendored
 * and kept diffable against their upstream archive. Declaring the props here
 * means the callbacks the app supplies are checked, so a renamed field or a
 * wrong return shape is a compile error rather than a silent no-op at
 * runtime.
 *
 * Keep in step with the props SignInCard actually destructures.
 */

/** Every callback resolves to this. `field` highlights one input. */
export type AuthResult = {
  ok: boolean
  error?: string
  field?: 'name' | 'email' | 'password'
  /** Greeting shown on the success step. */
  name?: string
}

export type SignInProps = {
  onEmailSignIn?: (email: string, password: string, remember: boolean) => Promise<AuthResult>
  onCreateAccount?: (input: {
    name: string
    email: string
    password: string
  }) => Promise<AuthResult>
  onForgotPassword?: (email: string) => Promise<AuthResult>
  onGuest?: () => void
  onDone?: () => void
  initialMode?: 'signin' | 'create' | 'forgot'
}

declare function SignInPage(props: SignInProps): JSX.Element
export default SignInPage

export declare function SignInCard(props: SignInProps): JSX.Element
export declare function SignInAside(): JSX.Element
